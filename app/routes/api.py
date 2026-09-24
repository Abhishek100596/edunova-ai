"""JSON API endpoints for charts and skill-gap data."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from app.models import CareerRole, PredictionRecord, ProgressRecord
from app.routes import ensure_student_profile, student_required
from app.services import skill_gap as skill_gap_svc

bp = Blueprint("api", __name__)


@bp.route("/readiness-history")
@login_required
@student_required
def readiness_history():
    """
    Chart data from PredictionRecord / ProgressRecord only.
    Returns chronological readiness and probability points.
    """
    profile = ensure_student_profile()

    progress = (
        ProgressRecord.query.filter_by(
            student_id=profile.id, metric_name="readiness"
        )
        .order_by(ProgressRecord.recorded_at.asc())
        .all()
    )
    predictions = (
        PredictionRecord.query.filter_by(student_id=profile.id)
        .order_by(PredictionRecord.created_at.asc())
        .all()
    )

    return jsonify(
        {
            "student_id": profile.id,
            "progress": [
                {
                    "recorded_at": p.recorded_at.isoformat() if p.recorded_at else None,
                    "metric_name": p.metric_name,
                    "metric_value": p.metric_value,
                }
                for p in progress
            ],
            "predictions": [
                {
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "probability": r.probability,
                    "readiness": r.readiness,
                }
                for r in predictions
            ],
        }
    )


@bp.route("/skill-gap")
@login_required
@student_required
def skill_gap_json():
    """JSON skill-gap analysis for a target role_id."""
    profile = ensure_student_profile()
    role_id = request.args.get("role_id", type=int)
    if not role_id:
        roles = CareerRole.query.order_by(CareerRole.name).all()
        return jsonify(
            {
                "error": "role_id query parameter is required",
                "available_roles": [
                    {"id": r.id, "name": r.name, "category": r.category} for r in roles
                ],
            }
        ), 400
    try:
        analysis = skill_gap_svc.gaps_for_role_id(profile, role_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify(analysis)


@bp.route("/opportunity-fit")
@login_required
@student_required
def opportunity_fit_json():
    """JSON opportunity fit rankings for the logged-in student."""
    profile = ensure_student_profile()
    try:
        from app.services.company_intel import opportunity_fit
    except ImportError:
        return jsonify(
            {
                "error": "company_intel service not available",
                "disclaimer": "Compatibility estimate, not a hiring guarantee.",
            }
        ), 503
    try:
        result = opportunity_fit(profile)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500
    if isinstance(result, list):
        payload = {
            "opportunities": result,
            "disclaimer": "Compatibility estimate, not a hiring guarantee.",
        }
    else:
        payload = result if isinstance(result, dict) else {"data": result}
        payload.setdefault(
            "disclaimer", "Compatibility estimate, not a hiring guarantee."
        )
    return jsonify(payload)


@bp.route("/intelligence-score")
@login_required
@student_required
def intelligence_score_json():
    """JSON EDUNOVA Intelligence Score breakdown for the logged-in student."""
    profile = ensure_student_profile()
    try:
        from app.services.intelligence_score import compute_intelligence_score
    except ImportError:
        return jsonify({"error": "intelligence_score service not available"}), 503
    try:
        return jsonify(compute_intelligence_score(profile))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@bp.route("/coach", methods=["POST"])
@login_required
@student_required
def coach_json():
    """JSON AI coach — uses the same service as the HTML coach UI."""
    profile = ensure_student_profile()
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400
    if len(message) > 2000:
        return jsonify({"error": "message too long (max 2000 characters)"}), 400
    try:
        from app.services import coach as coach_svc
    except ImportError:
        return jsonify({"error": "coach service not available"}), 503
    try:
        result = coach_svc.ask_coach(profile, message)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("API coach failed")
        return jsonify({"error": "Coach could not answer right now."}), 500
    if isinstance(result, dict):
        # Never return internal exception detail; keep presentation fields only
        return jsonify(
            {
                "provider": result.get("provider"),
                "reply": result.get("reply"),
                "reply_html": result.get("reply_html"),
                "fallback_used": result.get("fallback_used"),
                "status_message": result.get("status_message"),
            }
        )
    return jsonify({"reply": str(result)})


@bp.route("/health")
def health():
    """Public health — no secrets. Distinguishes AI configured vs unavailable."""
    from app.services.healthcheck import run_health_checks

    try:
        report = run_health_checks()
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Health check failed")
        return jsonify(
            {
                "status": "degraded",
                "service": "edunova-ai",
                "legacy": "nexora-ai",
                "ok": False,
                "database": "unknown",
                "ai": {"configured": False, "available": True},
            }
        ), 503

    db_ok = next(
        (c["ok"] for c in report.get("checks", []) if c.get("name") == "database"),
        False,
    )
    ai_check = next(
        (c for c in report.get("checks", []) if c.get("name") == "ai_provider"),
        {},
    )
    ml_ok = next(
        (c["ok"] for c in report.get("checks", []) if c.get("name") == "ml_model"),
        False,
    )
    provider = report.get("provider") or "local"
    key_set = "key=set" in str(ai_check.get("detail") or "")
    ai_configured = (provider == "local") or key_set or bool(ai_check.get("ok"))
    # App is healthy for Render if DB responds; AI/ML are soft status fields.
    payload = {
        "status": "ok" if db_ok else "degraded",
        "service": "edunova-ai",
        "legacy": "nexora-ai",
        "ok": bool(db_ok),
        "database": "connected" if db_ok else "error",
        "ml_model": "present" if ml_ok else "missing",
        "ai": {
            "provider": provider,
            "configured": bool(ai_configured),
            "available": True,  # local fallback always keeps features usable
            "detail": ai_check.get("detail") if isinstance(ai_check, dict) else None,
        },
        "demo_mode": bool(report.get("demo_mode")),
    }
    return jsonify(payload), (200 if db_ok else 503)
