"""Resolve AI credentials and call providers (local, gemini, openai, groq)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Mapping, Protocol, runtime_checkable

from app.ai.response import normalize_ai_text, safe_ai_error_message

logger = logging.getLogger(__name__)

# Configurable default — override with GROQ_MODEL or AI_MODEL.
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


@runtime_checkable
class AIProvider(Protocol):
    """Minimal chat interface used by coach / interview services."""

    name: str

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        context: Mapping[str, Any] | None = None,
        history: list[Mapping[str, Any]] | None = None,
    ) -> str:
        ...


def _format_context(context: Mapping[str, Any] | None) -> str:
    if not context:
        return ""
    parts: list[str] = []
    name = context.get("name")
    if name:
        parts.append(f"Student: {name}")
    skills = context.get("skills") or context.get("skill_names") or []
    if skills:
        if isinstance(skills, (list, tuple)):
            parts.append("Known skills: " + ", ".join(str(s) for s in skills[:20]))
        else:
            parts.append(f"Known skills: {skills}")
    for key, label in (
        ("degree", "Degree"),
        ("branch", "Branch"),
        ("cgpa", "CGPA"),
        ("college", "College"),
        ("graduation_year", "Graduation year"),
    ):
        val = context.get(key)
        if val is not None and val != "":
            parts.append(f"{label}: {val}")
    roles = context.get("preferred_roles")
    if roles:
        parts.append(f"Preferred roles: {roles}")
    targets = context.get("target_companies")
    if targets:
        parts.append(f"Target companies: {targets}")
    projects = context.get("project_summaries") or context.get("project_titles")
    if projects:
        if isinstance(projects, (list, tuple)):
            parts.append("Projects: " + "; ".join(str(p) for p in list(projects)[:6]))
        else:
            parts.append(f"Projects: {projects}")
    elif context.get("project_count") is not None:
        parts.append(f"Projects: {context.get('project_count')}")
    readiness = context.get("readiness_overall")
    if readiness is not None:
        parts.append(f"Readiness: {readiness}")
    top = context.get("top_role")
    if isinstance(top, dict) and top.get("role_name"):
        parts.append(f"Top match: {top.get('role_name')} ({top.get('match_pct')}%)")
        gaps = top.get("gaps") or []
        if gaps:
            gnames = []
            for g in gaps[:5]:
                gnames.append(g.get("skill_name") if isinstance(g, dict) else str(g))
            if gnames:
                parts.append("Top skill gaps: " + ", ".join(gnames))
    return " | ".join(parts)


def _history_messages(
    history: list[Mapping[str, Any]] | None, *, limit: int = 12
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for item in list(history or [])[-limit:]:
        role = str(item.get("role") or "user")
        content = str(item.get("message") or "").strip()
        if not content:
            continue
        mapped = "assistant" if role == "assistant" else "user"
        messages.append({"role": mapped, "content": content[:2000]})
    return messages


def _redact_secrets(text: str, secrets: list[str]) -> str:
    out = text or ""
    for secret in secrets:
        if secret and len(secret) > 6 and secret in out:
            out = out.replace(secret, "[REDACTED]")
    return out


def resolve_groq_credentials(app_config: Mapping[str, Any]) -> tuple[str, str]:
    """
    Accept both EduNova-native and Render-style env wiring:

    Preferred:
      GROQ_API_KEY + GROQ_MODEL
    Compatible (production docs):
      AI_PROVIDER=groq + AI_API_KEY + AI_MODEL
    """
    key = (
        str(app_config.get("GROQ_API_KEY", "") or "").strip()
        or str(app_config.get("AI_API_KEY", "") or "").strip()
    )
    model = (
        str(app_config.get("GROQ_MODEL", "") or "").strip()
        or str(app_config.get("AI_MODEL", "") or "").strip()
        or DEFAULT_GROQ_MODEL
    )
    return key, model


def _openai_compatible_complete(
    *,
    url: str,
    api_key: str,
    model: str,
    prompt: str,
    system: str | None,
    context: Mapping[str, Any] | None,
    history: list[Mapping[str, Any]] | None,
    temperature: float = 0.4,
    timeout: int = 60,
    provider_label: str = "openai-compatible",
) -> str:
    messages: list[dict[str, str]] = []
    system_parts = [system or "You are EDUNOVA AI, a career coach."]
    system_parts.append(
        "Never invent skills, projects, internships, certifications, or grades."
    )
    system_parts.append(
        "Answer in clear natural language for students. Do not return JSON unless explicitly asked."
    )
    ctx = _format_context(context)
    if ctx:
        system_parts.append(f"Student context: {ctx}")
    messages.append({"role": "system", "content": "\n".join(system_parts)})
    messages.extend(_history_messages(history))
    messages.append({"role": "user", "content": prompt or ""})

    payload = {"model": model, "messages": messages, "temperature": temperature}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        safe_body = _redact_secrets(body, [api_key])[:400]
        logger.warning("%s HTTP %s: %s", provider_label, exc.code, safe_body)
        if exc.code == 401:
            raise RuntimeError(f"{provider_label} authentication failed") from exc
        if exc.code == 429:
            raise RuntimeError(f"{provider_label} rate limit") from exc
        raise RuntimeError(f"{provider_label} HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        logger.warning("%s network error: %s", provider_label, getattr(exc, "reason", exc))
        raise RuntimeError(f"{provider_label} network error") from exc

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected {provider_label} response shape") from exc
    return normalize_ai_text(text)


class LocalProvider:
    """Deterministic local responses grounded in student context + history."""

    name = "local"

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        context: Mapping[str, Any] | None = None,
        history: list[Mapping[str, Any]] | None = None,
    ) -> str:
        skills = []
        if context:
            raw = context.get("skill_names") or context.get("skills") or []
            skills = list(raw) if isinstance(raw, (list, tuple)) else [str(raw)]
        prompt_l = (prompt or "").strip().lower()
        lines: list[str] = []

        if any(k in prompt_l for k in ("30 day", "30-day", "study plan")):
            focus = skills[0] if skills else "your top gap skill"
            lines.append(
                f"Here is a practical 30-day plan focused on {focus}:\n"
                f"1. Days 1–7: fundamentals and short exercises\n"
                f"2. Days 8–14: guided practice\n"
                f"3. Days 15–21: small project using {focus}\n"
                f"4. Days 22–30: polish, explain, and interview practice"
            )
        elif any(k in prompt_l for k in ("why should", "why that", "why learn")):
            focus = skills[0] if skills else "the recommended skill"
            lines.append(
                f"You should deepen {focus} because it strengthens evidence for your "
                "preferred role and closes a documented skill gap on your profile."
            )
        elif any(k in prompt_l for k in ("project should", "what project")):
            lines.append(
                "Build a small end-to-end portfolio project using skills already on your "
                "profile, then document outcomes and analyze the GitHub repo in EduNova."
            )
        elif any(k in prompt_l for k in ("learn", "gap", "roadmap", "missing")):
            if skills:
                lines.append(
                    "Next learning should prioritize documented gaps while reinforcing: "
                    + ", ".join(str(s) for s in skills[:8])
                    + "."
                )
            else:
                lines.append(
                    "Your profile has no skills recorded yet. Add skills and a target role "
                    "so EduNova can prioritize what to learn next."
                )
        elif any(k in prompt_l for k in ("resume", "cv")):
            lines.append(
                "Quantify outcomes on projects you already listed. Do not invent experience."
            )
        elif "interview" in prompt_l:
            lines.append(
                "Practice role-specific questions using only skills and projects on your profile. "
                "Use EduNova Interview Prep for scored practice."
            )
        else:
            lines.append(
                "I can help with what to learn next, why, a 30-day plan, project ideas, "
                "resume tips, or interview prep — based only on your saved EduNova profile."
            )
        return normalize_ai_text("\n".join(lines))


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str | None = None) -> None:
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip() or "gemini-1.5-flash"

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        context: Mapping[str, Any] | None = None,
        history: list[Mapping[str, Any]] | None = None,
    ) -> str:
        if not self.api_key:
            raise RuntimeError("GeminiProvider requires AI_API_KEY.")
        ctx = _format_context(context)
        hist_lines = []
        for m in _history_messages(history):
            hist_lines.append(f"{m['role'].upper()}: {m['content'][:800]}")
        parts: list[str] = []
        if system:
            parts.append(system)
        if ctx:
            parts.append(f"Student context:\n{ctx}")
        if hist_lines:
            parts.append("Recent conversation:\n" + "\n".join(hist_lines))
        parts.append(prompt or "")
        full_prompt = "\n\n".join(parts)

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        payload = {"contents": [{"parts": [{"text": full_prompt}]}]}
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = _redact_secrets(
                exc.read().decode("utf-8", errors="replace"), [self.api_key]
            )[:400]
            logger.warning("Gemini HTTP %s: %s", exc.code, body)
            raise RuntimeError(f"Gemini API HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            logger.warning("Gemini network error: %s", getattr(exc, "reason", exc))
            raise RuntimeError("Gemini API network error") from exc

        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Unexpected Gemini response shape") from exc
        return normalize_ai_text(text)


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str | None = None) -> None:
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip() or "gpt-4o-mini"

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        context: Mapping[str, Any] | None = None,
        history: list[Mapping[str, Any]] | None = None,
    ) -> str:
        if not self.api_key:
            raise RuntimeError("OpenAIProvider requires AI_API_KEY.")
        return _openai_compatible_complete(
            url="https://api.openai.com/v1/chat/completions",
            api_key=self.api_key,
            model=self.model,
            prompt=prompt,
            system=system,
            context=context,
            history=history,
            provider_label="OpenAI",
        )


class GroqProvider:
    """Groq chat completions via official SDK when available, else HTTP."""

    name = "groq"

    def __init__(self, api_key: str, model: str | None = None) -> None:
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip() or DEFAULT_GROQ_MODEL

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        context: Mapping[str, Any] | None = None,
        history: list[Mapping[str, Any]] | None = None,
    ) -> str:
        if not self.api_key:
            raise RuntimeError(
                "GroqProvider requires GROQ_API_KEY or AI_API_KEY when AI_PROVIDER=groq."
            )

        # Prefer official groq SDK if installed.
        try:
            from groq import Groq  # type: ignore
        except ImportError:
            Groq = None  # type: ignore

        if Groq is not None:
            system_parts = [system or "You are EDUNOVA AI, a career coach."]
            system_parts.append(
                "Never invent skills, projects, internships, certifications, or grades."
            )
            system_parts.append(
                "Answer in clear natural language for students. Do not return JSON unless asked."
            )
            ctx = _format_context(context)
            if ctx:
                system_parts.append(f"Student context: {ctx}")
            messages: list[dict[str, str]] = [
                {"role": "system", "content": "\n".join(system_parts)}
            ]
            messages.extend(_history_messages(history))
            messages.append({"role": "user", "content": prompt or ""})
            try:
                client = Groq(api_key=self.api_key)
                completion = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.45,
                )
                text = completion.choices[0].message.content or ""
                logger.info("Groq SDK success model=%s", self.model)
                return normalize_ai_text(text)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Groq SDK failed (%s); trying HTTP. Detail: %s",
                    type(exc).__name__,
                    safe_ai_error_message(exc),
                )

        return _openai_compatible_complete(
            url=f"{GROQ_BASE_URL}/chat/completions",
            api_key=self.api_key,
            model=self.model,
            prompt=prompt,
            system=system,
            context=context,
            history=history,
            temperature=0.45,
            provider_label="Groq",
        )


def get_ai_provider(app_config: Mapping[str, Any]) -> AIProvider:
    """Factory: local | gemini | openai | groq from app config."""
    provider = str(app_config.get("AI_PROVIDER", "local") or "local").strip().lower()
    api_key = str(app_config.get("AI_API_KEY", "") or "").strip()
    model = str(app_config.get("AI_MODEL", "") or "").strip() or None

    if provider in {"local", "demo", "local-demo"}:
        return LocalProvider()
    if provider in {"gemini", "google"}:
        return GeminiProvider(api_key=api_key, model=model)
    if provider in {"openai", "gpt"}:
        return OpenAIProvider(api_key=api_key, model=model)
    if provider in {"groq"}:
        groq_key, groq_model = resolve_groq_credentials(app_config)
        return GroqProvider(api_key=groq_key, model=groq_model)

    raise ValueError(
        f"Unknown AI_PROVIDER={provider!r}. Use local, gemini, openai, or groq."
    )


def _provider_chain(app_config: Mapping[str, Any]) -> list[AIProvider]:
    """Primary → other configured clouds → local. Never reuse Groq key as OpenAI."""
    primary_name = str(app_config.get("AI_PROVIDER", "local") or "local").strip().lower()
    chain: list[AIProvider] = []
    seen: set[str] = set()

    def _add(p: AIProvider) -> None:
        if p.name in seen:
            return
        seen.add(p.name)
        chain.append(p)

    try:
        _add(get_ai_provider(app_config))
    except Exception as exc:
        logger.warning("Primary provider unavailable: %s", safe_ai_error_message(exc))

    groq_key, groq_model = resolve_groq_credentials(app_config)
    openai_or_gemini_key = str(app_config.get("AI_API_KEY", "") or "").strip()
    ai_model = str(app_config.get("AI_MODEL", "") or "").strip() or None
    dedicated_groq = str(app_config.get("GROQ_API_KEY", "") or "").strip()

    # Only add Groq as secondary if it wasn't primary and we have a key.
    if primary_name != "groq" and groq_key:
        _add(GroqProvider(api_key=groq_key, model=groq_model))

    # Gemini/OpenAI secondary only when primary is NOT groq using shared AI_API_KEY,
    # OR when a dedicated GROQ_API_KEY exists so AI_API_KEY can mean OpenAI/Gemini.
    if openai_or_gemini_key and primary_name not in {"openai", "gpt", "gemini", "google"}:
        if primary_name == "groq" and not dedicated_groq:
            # AI_API_KEY is the Groq key — do not also try OpenAI with it.
            pass
        else:
            fallback = str(app_config.get("AI_FALLBACK_PROVIDER", "openai") or "openai").lower()
            if fallback in {"gemini", "google"}:
                _add(GeminiProvider(api_key=openai_or_gemini_key, model=ai_model))
            else:
                _add(OpenAIProvider(api_key=openai_or_gemini_key, model=ai_model))

    _add(LocalProvider())
    return chain


def complete_with_fallback(
    app_config: Mapping[str, Any],
    prompt: str,
    *,
    system: str | None = None,
    context: Mapping[str, Any] | None = None,
    history: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Try primary then configured fallbacks once each; always return normalized text.

    DEMO_MODE does not force local — only AI_PROVIDER=local does.
    """
    chain = _provider_chain(app_config)
    primary = str(app_config.get("AI_PROVIDER", "local") or "local").strip().lower()
    primary_aliases = {
        "local": {"local", "demo", "local-demo"},
        "groq": {"groq"},
        "openai": {"openai", "gpt"},
        "gemini": {"gemini", "google"},
    }
    aliases = primary_aliases.get(primary, {primary})

    logger.info(
        "AI request primary=%s chain=%s",
        primary,
        [p.name for p in chain],
    )

    for provider in chain:
        try:
            reply = provider.complete(
                prompt, system=system, context=context, history=history
            )
            reply = normalize_ai_text(reply)
            is_primary = provider.name in aliases
            status = ""
            if not is_primary:
                status = "AI provider temporarily unavailable. Using EduNova fallback."
            logger.info("AI success provider=%s primary=%s", provider.name, is_primary)
            return {
                "reply": reply,
                "provider": provider.name,
                "fallback_used": not is_primary,
                "status_message": status,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Provider %s failed: %s", provider.name, type(exc).__name__
            )
            continue

    return {
        "reply": normalize_ai_text(
            "I could not reach an AI provider right now. Please try again shortly, "
            "or ask about readiness, skill gaps, or interview prep based on your saved profile."
        ),
        "provider": "local",
        "fallback_used": True,
        "status_message": "AI provider temporarily unavailable. Using EduNova fallback.",
    }
