"""JSON API endpoints for charts and skill-gap data."""

from __future__ import annotations

from flask import Blueprint, jsonify, request
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
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": "Coach could not answer right now.", "detail": str(exc)[:160]}), 500
    if isinstance(result, dict):
        return jsonify(result)
    return jsonify({"reply": str(result)})


@bp.route("/health")
def health():
    return jsonify({"status": "ok", "service": "edunova-ai", "legacy": "nexora-ai"})
