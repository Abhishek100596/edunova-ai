"""Normalize AI model output for safe, human-readable presentation."""

from __future__ import annotations

import ast
import json
import re
from typing import Any


_FENCE_RE = re.compile(r"```(?:json|python|javascript|text|markdown|md)?\s*\n?(.*?)```", re.I | re.S)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_unwanted_code_fences(text: str) -> str:
    """Remove surrounding code fences while keeping inner content."""
    if not text:
        return ""
    stripped = text.strip()
    # Whole-message fence
    m = re.fullmatch(r"```(?:\w+)?\s*\n?(.*?)```", stripped, re.I | re.S)
    if m:
        return m.group(1).strip()
    # Replace remaining fences with their content
    return _FENCE_RE.sub(lambda m: m.group(1).strip(), stripped).strip()


def extract_text_from_response(raw: Any) -> str:
    """Pull plain text from provider payloads / nested structures."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, (int, float, bool)):
        return str(raw)
    if isinstance(raw, dict):
        for key in (
            "answer",
            "reply",
            "message",
            "content",
            "text",
            "feedback",
            "summary",
            "output",
        ):
            if key in raw and raw[key] is not None:
                return extract_text_from_response(raw[key])
        # OpenAI-style
        try:
            return extract_text_from_response(raw["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError):
            pass
        try:
            return extract_text_from_response(
                raw["candidates"][0]["content"]["parts"][0]["text"]
            )
        except (KeyError, IndexError, TypeError):
            pass
        return ""
    if isinstance(raw, (list, tuple)):
        parts = [extract_text_from_response(x) for x in raw]
        return "\n".join(p for p in parts if p)
    return str(raw).strip()


def _try_parse_structured(text: str) -> Any | None:
    t = text.strip()
    if not t:
        return None
    if (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]")):
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            try:
                return ast.literal_eval(t)
            except (ValueError, SyntaxError, MemoryError):
                return None
    return None


def _dict_to_readable(data: dict[str, Any]) -> str:
    lines: list[str] = []
    priority = [
        "answer",
        "reply",
        "feedback",
        "summary",
        "score",
        "strengths",
        "weaknesses",
        "missing_points",
        "better_answer_outline",
        "recommendations",
    ]
    used = set()
    for key in priority:
        if key not in data:
            continue
        used.add(key)
        val = data[key]
        label = key.replace("_", " ").title()
        if isinstance(val, list):
            lines.append(f"{label}:")
            for item in val:
                lines.append(f"• {extract_text_from_response(item)}")
        elif key == "score":
            lines.append(f"Score: {val}/100" if str(val).replace(".", "", 1).isdigit() else f"Score: {val}")
        else:
            lines.append(f"{label}:\n{extract_text_from_response(val)}")
    for key, val in data.items():
        if key in used:
            continue
        if key.lower() in {"id", "meta", "raw", "provider", "model"}:
            continue
        label = str(key).replace("_", " ").title()
        if isinstance(val, list):
            lines.append(f"{label}:")
            for item in val[:12]:
                lines.append(f"• {extract_text_from_response(item)}")
        elif isinstance(val, dict):
            lines.append(f"{label}:\n{_dict_to_readable(val)}")
        else:
            text = extract_text_from_response(val)
            if text:
                lines.append(f"{label}: {text}")
    return "\n\n".join(lines).strip()


def clean_markdown(text: str) -> str:
    """Light cleanup that preserves useful markdown structure."""
    if not text:
        return ""
    # Strip accidental HTML tags (Jinja will escape remaining text)
    text = _HTML_TAG_RE.sub("", text)
    # Normalize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_ai_text(raw: Any) -> str:
    """
    Convert model output into presentation-ready plain/Markdown text.

    Never returns Python repr / raw JSON blobs when a readable form exists.
    """
    text = extract_text_from_response(raw)
    text = strip_unwanted_code_fences(text)
    structured = _try_parse_structured(text)
    if isinstance(structured, dict):
        text = _dict_to_readable(structured)
    elif isinstance(structured, list):
        text = "\n".join(f"• {extract_text_from_response(x)}" for x in structured)
    text = clean_markdown(text)
    # Final guard: if still looks like a bare dict string, soften it
    if (text.startswith("{") and ("'answer'" in text or '"answer"' in text)) or text.startswith(
        '{"'
    ):
        again = _try_parse_structured(text)
        if isinstance(again, dict):
            text = _dict_to_readable(again)
    # Soften accidental Python dict reprs that literal_eval couldn't parse
    if text.startswith("{") and ("': " in text or "':\n" in text):
        softened = text
        for token in ("{", "}", "'"):
            softened = softened.replace(token, " ")
        softened = re.sub(r"\s+", " ", softened).strip()
        if softened and len(softened) > 8:
            text = softened
    return text.strip()


def normalize_ai_response(raw: Any) -> dict[str, Any]:
    """
    Central AI response normalization for all GenAI features.

    Returns a stable internal shape:
      { "text": str, "html": str, "ok": bool }
    Accepts strings, dicts, lists, nested provider payloads, and SDK-like objects.
    """
    text = normalize_ai_text(raw)
    if not text:
        return {
            "text": "",
            "html": "",
            "ok": False,
        }
    return {
        "text": text,
        "html": markdown_to_safe_html(text),
        "ok": True,
    }


def format_interview_evaluation(data: dict[str, Any]) -> str:
    """Render structured interview evaluation for students."""
    score = data.get("score")
    lines: list[str] = []
    if score is not None:
        try:
            lines.append(f"Score: {float(score):.0f}/100")
        except (TypeError, ValueError):
            lines.append(f"Score: {score}/100")

    mode = data.get("evaluation_mode") or data.get("mode")
    if mode:
        lines.append(f"Evaluation: {mode}")

    def _bullets(title: str, items: Any) -> None:
        if not items:
            return
        lines.append("")
        lines.append(f"{title}:")
        if isinstance(items, str):
            lines.append(f"• {items}")
            return
        for item in list(items)[:8]:
            lines.append(f"• {extract_text_from_response(item)}")

    _bullets("What you did well", data.get("strengths"))
    _bullets("What to improve", data.get("weaknesses"))
    _bullets("Missing points", data.get("missing_points") or data.get("missing_keywords"))
    outline = data.get("better_answer_outline") or data.get("feedback")
    if outline and not data.get("strengths"):
        # Already have score; add narrative feedback block
        lines.append("")
        lines.append("Feedback:")
        lines.append(normalize_ai_text(outline))
    elif data.get("better_answer_outline"):
        lines.append("")
        lines.append("How to answer better:")
        lines.append(normalize_ai_text(data["better_answer_outline"]))
    elif data.get("feedback") and data.get("strengths"):
        lines.append("")
        lines.append("Coach notes:")
        lines.append(normalize_ai_text(data["feedback"]))

    return "\n".join(lines).strip()


def safe_ai_error_message(exc: BaseException | str | None = None) -> str:
    """User-facing error without secrets or stack traces."""
    _ = exc  # intentionally unused — never surface exception text to students
    return (
        "The AI assistant is temporarily unavailable. "
        "EduNova is using a safe fallback based on your saved profile."
    )


def markdown_to_safe_html(text: str) -> str:
    """
    Minimal Markdown → HTML for coach bubbles.

    Escapes HTML first, then applies limited formatting.
    """
    import html as html_mod

    raw = normalize_ai_text(text)
    escaped = html_mod.escape(raw)
    # Bold **text**
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    # Italic *text* (avoid bullets)
    escaped = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", escaped)
    # Headings
    escaped = re.sub(r"^### (.+)$", r"<strong>\1</strong>", escaped, flags=re.M)
    escaped = re.sub(r"^## (.+)$", r"<strong>\1</strong>", escaped, flags=re.M)
    escaped = re.sub(r"^# (.+)$", r"<strong>\1</strong>", escaped, flags=re.M)
    # Unordered list lines
    lines = escaped.split("\n")
    out: list[str] = []
    in_list = False
    for line in lines:
        bullet = re.match(r"^[\-\*•]\s+(.+)$", line)
        numbered = re.match(r"^(\d+)\.\s+(.+)$", line)
        if bullet:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{bullet.group(1)}</li>")
        elif numbered:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{numbered.group(1)}. {numbered.group(2)}</li>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            if line.strip():
                out.append(f"{line}<br>")
            else:
                out.append("<br>")
    if in_list:
        out.append("</ul>")
    html = "".join(out)
    html = re.sub(r"(<br>){3,}", "<br><br>", html)
    return html
