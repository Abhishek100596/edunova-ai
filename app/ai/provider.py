"""AI provider protocol and implementations (local, gemini, openai, groq)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Mapping, Protocol, runtime_checkable

from app.ai.response import normalize_ai_text, safe_ai_error_message

logger = logging.getLogger(__name__)

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
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
    return " | ".join(parts)


def _format_history(history: list[Mapping[str, Any]] | None, *, limit: int = 12) -> str:
    if not history:
        return ""
    lines: list[str] = []
    for item in list(history)[-limit:]:
        role = str(item.get("role") or "user")
        msg = str(item.get("message") or "").strip()
        if not msg:
            continue
        lines.append(f"{role.upper()}: {msg[:800]}")
    return "\n".join(lines)


def _redact_secrets(text: str, secrets: list[str]) -> str:
    out = text or ""
    for secret in secrets:
        if secret and secret in out:
            out = out.replace(secret, "[REDACTED]")
    return out


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
    timeout: int = 45,
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
    for item in (history or [])[-12:]:
        role = str(item.get("role") or "user")
        content = str(item.get("message") or "").strip()
        if not content:
            continue
        mapped = "assistant" if role == "assistant" else "user"
        messages.append({"role": mapped, "content": content[:2000]})
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
        raise RuntimeError(f"{provider_label} HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        logger.warning("%s network error: %s", provider_label, exc.reason)
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
    """Google Gemini REST — requires AI_API_KEY."""

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
        hist = _format_history(history)
        parts: list[str] = []
        if system:
            parts.append(system)
        if ctx:
            parts.append(f"Student context:\n{ctx}")
        if hist:
            parts.append(f"Recent conversation:\n{hist}")
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
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = _redact_secrets(
                exc.read().decode("utf-8", errors="replace"), [self.api_key]
            )[:400]
            logger.warning("Gemini HTTP %s: %s", exc.code, body)
            raise RuntimeError(f"Gemini API HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            logger.warning("Gemini network error: %s", exc.reason)
            raise RuntimeError("Gemini API network error") from exc

        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Unexpected Gemini response shape") from exc
        return normalize_ai_text(text)


class OpenAIProvider:
    """OpenAI Chat Completions — requires AI_API_KEY."""

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
    """Groq OpenAI-compatible Chat Completions — requires GROQ_API_KEY."""

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
                "GroqProvider requires GROQ_API_KEY. Set GROQ_API_KEY or use AI_PROVIDER=local."
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
    api_key = str(app_config.get("AI_API_KEY", "") or "")
    model = str(app_config.get("AI_MODEL", "") or "") or None
    groq_key = str(app_config.get("GROQ_API_KEY", "") or "")
    groq_model = str(app_config.get("GROQ_MODEL", "") or "") or None

    if provider in {"local", "demo", "local-demo"}:
        return LocalProvider()
    if provider in {"gemini", "google"}:
        return GeminiProvider(api_key=api_key, model=model)
    if provider in {"openai", "gpt"}:
        return OpenAIProvider(api_key=api_key, model=model)
    if provider in {"groq"}:
        return GroqProvider(api_key=groq_key or api_key, model=groq_model or model)

    raise ValueError(
        f"Unknown AI_PROVIDER={provider!r}. Use local, gemini, openai, or groq."
    )


def _provider_chain(app_config: Mapping[str, Any]) -> list[AIProvider]:
    """Ordered unique providers: primary → other configured clouds → local."""
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

    groq_key = str(app_config.get("GROQ_API_KEY", "") or "").strip()
    openai_key = str(app_config.get("AI_API_KEY", "") or "").strip()
    ai_model = str(app_config.get("AI_MODEL", "") or "") or None
    groq_model = str(app_config.get("GROQ_MODEL", "") or "") or None

    if groq_key and primary_name != "groq":
        _add(GroqProvider(api_key=groq_key, model=groq_model or ai_model))

    # If primary is groq and it failed construction, already handled.
    # Offer gemini/openai when AI_API_KEY present and provider not already primary.
    if openai_key:
        if primary_name not in {"openai", "gpt"}:
            # Prefer openai as secondary cloud when key present; gemini also uses AI_API_KEY
            # Only add the one matching AI_PROVIDER preference if gemini, else openai.
            preferred_secondary = str(app_config.get("AI_FALLBACK_PROVIDER", "") or "").lower()
            if preferred_secondary in {"gemini", "google"} or primary_name in {
                "gemini",
                "google",
            }:
                if primary_name not in {"gemini", "google"}:
                    _add(GeminiProvider(api_key=openai_key, model=ai_model))
            if primary_name not in {"openai", "gpt"}:
                _add(OpenAIProvider(api_key=openai_key, model=ai_model))
            if primary_name not in {"gemini", "google"} and preferred_secondary in {
                "gemini",
                "google",
            }:
                pass
            elif primary_name not in {"gemini", "google"} and not preferred_secondary:
                # Also allow gemini with same key if explicitly wanted later — skip duplicate noise
                pass

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

    Returns:
      { reply, provider, fallback_used, status_message }
    """
    chain = _provider_chain(app_config)
    errors: list[str] = []
    for idx, provider in enumerate(chain):
        try:
            reply = provider.complete(
                prompt, system=system, context=context, history=history
            )
            reply = normalize_ai_text(reply)
            fallback_used = idx > 0 or provider.name == "local" and str(
                app_config.get("AI_PROVIDER", "local")
            ).lower() not in {"local", "demo", "local-demo"}
            # More precise: fallback if not the configured primary name
            primary = str(app_config.get("AI_PROVIDER", "local") or "local").strip().lower()
            primary_aliases = {
                "local": {"local", "demo", "local-demo"},
                "groq": {"groq"},
                "openai": {"openai", "gpt"},
                "gemini": {"gemini", "google"},
            }
            aliases = primary_aliases.get(primary, {primary})
            is_primary = provider.name in aliases or (
                provider.name == "local" and primary in {"local", "demo", "local-demo"}
            )
            status = ""
            if not is_primary:
                status = "AI provider temporarily unavailable. Using EduNova fallback."
                fallback_used = True
            return {
                "reply": reply,
                "provider": provider.name,
                "fallback_used": bool(fallback_used) and not is_primary,
                "status_message": status,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Provider %s failed: %s", provider.name, safe_ai_error_message(exc)
            )
            errors.append(provider.name)
            continue

    return {
        "reply": normalize_ai_text(
            "I could not reach an AI provider right now. Please update your profile "
            "skills and try again, or ask about readiness, skill gaps, or interview prep."
        ),
        "provider": "local",
        "fallback_used": True,
        "status_message": "AI provider temporarily unavailable. Using EduNova fallback.",
    }
