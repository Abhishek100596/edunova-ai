"""AI provider protocol and implementations."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Mapping, Protocol, runtime_checkable


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
    skills = context.get("skills") or []
    if skills:
        if isinstance(skills, (list, tuple)):
            parts.append("Known skills: " + ", ".join(str(s) for s in skills))
        else:
            parts.append(f"Known skills: {skills}")
    cgpa = context.get("cgpa")
    if cgpa is not None:
        parts.append(f"CGPA: {cgpa}")
    branch = context.get("branch")
    if branch:
        parts.append(f"Branch: {branch}")
    roles = context.get("preferred_roles")
    if roles:
        parts.append(f"Preferred roles: {roles}")
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


class LocalProvider:
    """Deterministic local responses grounded in student context + history."""

    name = "local-demo"

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        context: Mapping[str, Any] | None = None,
        history: list[Mapping[str, Any]] | None = None,
    ) -> str:
        ctx = _format_context(context)
        hist = _format_history(history)
        prompt_l = (prompt or "").strip().lower()
        skills = []
        if context:
            raw = context.get("skill_names") or context.get("skills") or []
            skills = list(raw) if isinstance(raw, (list, tuple)) else [str(raw)]

        lines = [
            "[LocalProvider] Context-aware local response (not a live cloud LLM).",
        ]
        if ctx:
            lines.append(f"Context used: {ctx}")
        if hist:
            # Include a short digest so follow-ups differ from cold starts.
            last_user = ""
            for item in reversed(list(history or [])):
                if str(item.get("role")) == "user":
                    last_user = str(item.get("message") or "")[:160]
                    break
            if last_user:
                lines.append(f"Prior user turn considered: {last_user}")

        if any(k in prompt_l for k in ("30 day", "30-day", "study plan")):
            focus = skills[0] if skills else "your top gap skill"
            lines.append(
                f"30-day local plan for {focus}: fundamentals → practice → mini-project → interview stories."
            )
        elif any(k in prompt_l for k in ("why should", "why that", "why learn")):
            focus = skills[0] if skills else "the recommended skill"
            lines.append(
                f"Why {focus}: it strengthens evidence for your preferred role and closes a catalog gap."
            )
        elif any(k in prompt_l for k in ("project should", "what project")):
            lines.append(
                "Project idea: build a small end-to-end demo using skills already on your profile, then analyze the GitHub repo in EduNova."
            )
        elif any(k in prompt_l for k in ("learn", "gap", "roadmap", "missing")):
            if skills:
                lines.append(
                    "Next learning should prioritize documented gaps while reinforcing "
                    f"({', '.join(str(s) for s in skills[:8])})."
                )
            else:
                lines.append(
                    "No skills on file yet — complete your skill profile before requesting a personalized roadmap."
                )
        elif any(k in prompt_l for k in ("resume", "cv")):
            lines.append(
                "Resume tip: quantify impact on projects you already listed; do not invent experience."
            )
        elif "interview" in prompt_l:
            lines.append(
                "Interview tip: practice role-specific questions using only skills and projects on file."
            )
        else:
            lines.append(
                "Career coaching: answer is grounded in your saved profile. Ask about learning next, why, a 30-day plan, projects, or interviews."
            )

        lines.append(f"Your question: {(prompt or '').strip()[:400]}")
        return "\n".join(lines)


class GeminiProvider:
    """Google Gemini REST stub — requires AI_API_KEY."""

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
            raise RuntimeError(
                "GeminiProvider requires AI_API_KEY. Set AI_API_KEY in the "
                "environment or use AI_PROVIDER=local."
            )
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
        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
        }
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
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini API HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Gemini API network error: {exc}") from exc

        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected Gemini response: {data}") from exc


class OpenAIProvider:
    """OpenAI Chat Completions REST stub — requires AI_API_KEY."""

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
            raise RuntimeError(
                "OpenAIProvider requires AI_API_KEY. Set AI_API_KEY in the "
                "environment or use AI_PROVIDER=local."
            )
        ctx = _format_context(context)
        messages: list[dict[str, str]] = []
        system_parts = [system or "You are EDUNOVA AI, a career coach."]
        system_parts.append(
            "Never invent skills, projects, or experience the student does not have."
        )
        system_parts.append(
            "Answer the current user question; use prior turns only for follow-up context."
        )
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

        payload = {"model": self.model, "messages": messages, "temperature": 0.4}
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenAI API network error: {exc}") from exc

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected OpenAI response: {data}") from exc


def get_ai_provider(app_config: Mapping[str, Any]) -> AIProvider:
    """Factory: local | gemini | openai from app config."""
    provider = str(app_config.get("AI_PROVIDER", "local") or "local").strip().lower()
    api_key = str(app_config.get("AI_API_KEY", "") or "")
    model = str(app_config.get("AI_MODEL", "") or "") or None

    if provider in {"local", "demo", "local-demo"}:
        return LocalProvider()
    if provider in {"gemini", "google"}:
        return GeminiProvider(api_key=api_key, model=model)
    if provider in {"openai", "gpt"}:
        return OpenAIProvider(api_key=api_key, model=model)

    raise ValueError(
        f"Unknown AI_PROVIDER={provider!r}. Use local, gemini, or openai."
    )
