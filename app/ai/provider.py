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
    projects = context.get("project_count")
    if projects is not None:
        parts.append(f"Projects: {projects}")
    return " | ".join(parts)


class LocalProvider:
    """Deterministic demo responses grounded in provided student context."""

    name = "local-demo"

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> str:
        ctx = _format_context(context)
        skills = []
        if context:
            raw = context.get("skills") or []
            skills = list(raw) if isinstance(raw, (list, tuple)) else [str(raw)]

        prompt_l = (prompt or "").strip().lower()
        lines = [
            "[DEMO — LocalProvider] This response is a deterministic demo, "
            "not a live LLM.",
        ]
        if ctx:
            lines.append(f"Context used: {ctx}")
        if system:
            lines.append(f"System focus: {system[:200]}")

        if any(k in prompt_l for k in ("interview", "answer", "evaluate")):
            lines.append(
                "AI-assisted evaluation hint: cover situation, actions, and "
                "measurable outcome; reference only skills you actually have"
                + (f" ({', '.join(skills)})." if skills else ".")
            )
        elif any(k in prompt_l for k in ("roadmap", "learn", "gap")):
            if skills:
                lines.append(
                    "Focus next learning on strengthening existing skills "
                    f"({', '.join(skills[:8])}) before adding new ones."
                )
            else:
                lines.append(
                    "No skills on file yet — complete your skill profile before "
                    "requesting a personalized roadmap."
                )
        elif any(k in prompt_l for k in ("resume", "cv")):
            lines.append(
                "Resume tip: quantify impact on projects you already listed; "
                "do not invent experience or certifications."
            )
        else:
            if skills:
                lines.append(
                    "Career coaching (demo): build on your documented skills — "
                    f"{', '.join(skills[:10])}. Ask about interview prep, "
                    "skill gaps, or placement readiness for more detail."
                )
            else:
                lines.append(
                    "Career coaching (demo): your profile has no skills recorded. "
                    "Add verified skills so advice stays accurate."
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
    ) -> str:
        if not self.api_key:
            raise RuntimeError(
                "GeminiProvider requires AI_API_KEY. Set AI_API_KEY in the "
                "environment or use AI_PROVIDER=local."
            )
        ctx = _format_context(context)
        parts: list[str] = []
        if system:
            parts.append(system)
        if ctx:
            parts.append(f"Student context:\n{ctx}")
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
        if ctx:
            system_parts.append(f"Student context: {ctx}")
        messages.append({"role": "system", "content": "\n".join(system_parts)})
        messages.append({"role": "user", "content": prompt or ""})

        payload = {"model": self.model, "messages": messages, "temperature": 0.2}
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
