"""Shared AI narrative helpers — explain deterministic results, never invent facts."""

from __future__ import annotations

import logging
from typing import Any, Mapping

from flask import current_app

from app.ai.provider import complete_with_fallback
from app.ai.response import markdown_to_safe_html, normalize_ai_text, safe_ai_error_message

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are EDUNOVA AI, an educational career coach. "
    "Explain results in clear student-friendly Markdown. "
    "Never invent skills, projects, grades, internships, certifications, or employers. "
    "If data is missing, say it is missing. "
    "Do not return JSON, Python dictionaries, or code fences unless the student asked for code."
)


def generate_narrative(
    prompt: str,
    *,
    context: Mapping[str, Any] | None = None,
    system: str | None = None,
) -> dict[str, Any]:
    """
    Produce normalized text via the shared provider chain.

    Always returns a dict with reply / reply_html / provider / fallback_used.
    Never raises to callers for provider failures.
    """
    cfg = current_app.config
    try:
        result = complete_with_fallback(
            cfg,
            prompt,
            system=system or _SYSTEM,
            context=context,
        )
        reply = normalize_ai_text(result.get("reply") or "")
        return {
            "reply": reply,
            "reply_html": markdown_to_safe_html(reply),
            "provider": result.get("provider") or "local",
            "fallback_used": bool(result.get("fallback_used")),
            "ok": bool(reply),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI narrative failed: %s", safe_ai_error_message(exc))
        msg = safe_ai_error_message(exc)
        return {
            "reply": msg,
            "reply_html": markdown_to_safe_html(msg),
            "provider": "local",
            "fallback_used": True,
            "ok": False,
        }
