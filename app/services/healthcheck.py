"""Demo / presentation health checks — never exposes secrets."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from flask import current_app

from app.extensions import db
from app.models import CareerRole, Skill, User


def run_health_checks() -> dict[str, Any]:
    """Aggregate safe diagnostic checks for college demos."""
    checks: list[dict[str, Any]] = []

    try:
        db.session.execute(db.text("SELECT 1"))
        skill_count = Skill.query.count()
        role_count = CareerRole.query.count()
        demo = User.query.filter(
            User.email.in_(["demo@edunova.ai", "demo@nexora.ai"])
        ).first()
        checks.append(
            {
                "name": "database",
                "ok": True,
                "detail": f"Connected — {skill_count} skills, {role_count} roles"
                + (", demo account present" if demo else ", demo account missing"),
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            {
                "name": "database",
                "ok": False,
                "detail": f"Database check failed ({type(exc).__name__})",
            }
        )

    provider = str(current_app.config.get("AI_PROVIDER") or "local").lower()
    has_key = bool(
        str(current_app.config.get("GROQ_API_KEY") or "").strip()
        or str(current_app.config.get("AI_API_KEY") or "").strip()
    )
    model = (
        str(current_app.config.get("GROQ_MODEL") or "").strip()
        or str(current_app.config.get("AI_MODEL") or "").strip()
        or "openai/gpt-oss-120b"
    )
    if provider == "groq":
        ai_ok = has_key
        ai_detail = (
            f"Groq configured (model={model}, key={'set' if has_key else 'missing'})"
        )
    elif provider in {"openai", "gpt", "gemini", "google"}:
        ai_ok = has_key
        ai_detail = f"Provider={provider}, key={'set' if has_key else 'missing'}"
    else:
        ai_ok = True
        ai_detail = "Local / demo provider — offline fallback active"
    checks.append({"name": "ai_provider", "ok": ai_ok, "detail": ai_detail})

    model_path = Path(current_app.config.get("ML_MODEL_PATH") or "")
    meta_path = Path(current_app.config.get("ML_META_PATH") or "")
    ml_ok = model_path.is_file()
    checks.append(
        {
            "name": "ml_model",
            "ok": ml_ok,
            "detail": (
                f"Placement model {'found' if ml_ok else 'missing'} at configured path"
                + ("; meta present" if meta_path.is_file() else "; meta missing")
            ),
        }
    )

    templates = [
        "student/dashboard.html",
        "student/coach.html",
        "student/interview.html",
        "student/what_if.html",
        "student/jd_analyzer.html",
        "student/learning.html",
    ]
    root = Path(current_app.root_path) / "templates"
    missing = [t for t in templates if not (root / t).is_file()]
    checks.append(
        {
            "name": "critical_templates",
            "ok": not missing,
            "detail": "All critical templates present"
            if not missing
            else f"Missing: {', '.join(missing)}",
        }
    )

    checks.append(
        {
            "name": "secret_key",
            "ok": bool(current_app.config.get("SECRET_KEY")),
            "detail": "SECRET_KEY is set"
            if current_app.config.get("SECRET_KEY")
            else "SECRET_KEY missing",
        }
    )

    overall = all(c["ok"] for c in checks)
    return {
        "ok": overall,
        "provider": provider,
        "model": model if provider == "groq" else None,
        "demo_mode": bool(current_app.config.get("DEMO_MODE")),
        "checks": checks,
        "flask_env": os.environ.get("FLASK_ENV") or "unset",
    }
