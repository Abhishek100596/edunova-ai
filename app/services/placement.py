"""Placement probability and readiness — deterministic, never random."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from flask import current_app

from app.models.experience import Certification, Internship, Project
from app.models.interview import InterviewSession
from app.models.profile import StudentProfile
from app.models.skills import StudentSkill
from app.utils.readiness import compute_all_readiness, overall_readiness

SYNTHETIC_ML_DISCLAIMER = (
    "EDUNOVA AI placement probability may use a model trained on synthetic / "
    "illustrative data. Scores are educational readiness estimates only — "
    "not hiring decisions, guarantees, or live employer outcomes."
)

# Must match ml/datasets + ml/training/train_placement FEATURE_NAMES.
FEATURE_NAMES = [
    "cgpa",
    "attendance",
    "backlogs",
    "skill_count",
    "avg_skill_level",
    "project_count",
    "internship_count",
    "certification_count",
    "hackathon_count",
]


def _clamp01(x: float) -> float:
    return float(max(0.0, min(1.0, x)))


def build_feature_vector(profile: StudentProfile) -> dict[str, float]:
    """Compute a fixed feature vector from real profile / related DB fields."""
    skills = StudentSkill.query.filter_by(student_id=profile.id).all()
    skill_count = len(skills)
    avg_level = (
        sum(max(1, min(5, int(s.level or 1))) for s in skills) / skill_count
        if skill_count
        else 0.0
    )
    projects = Project.query.filter_by(student_id=profile.id).count()
    internships = Internship.query.filter_by(student_id=profile.id).count()
    certs = Certification.query.filter_by(student_id=profile.id).count()

    cgpa = float(profile.cgpa) if profile.cgpa is not None else 0.0
    if 0 < cgpa <= 4.0:
        cgpa = cgpa * 2.5

    attendance = float(profile.attendance) if profile.attendance is not None else 0.0
    if 0 < attendance <= 1.0:
        attendance = attendance * 100.0

    # No dedicated hackathon table — approximate from completed interviews / projects.
    completed_interviews = InterviewSession.query.filter_by(
        student_id=profile.id, status="completed"
    ).count()
    hackathon_count = min(5, max(0, completed_interviews // 2 + (1 if projects >= 3 else 0)))

    features = {
        "cgpa": round(cgpa, 2),
        "attendance": round(attendance, 1),
        "backlogs": float(int(profile.backlogs or 0)),
        "skill_count": float(skill_count),
        "avg_skill_level": round(float(avg_level), 2),
        "project_count": float(projects),
        "internship_count": float(internships),
        "certification_count": float(certs),
        "hackathon_count": float(hackathon_count),
    }
    return features


def _vector_array(features: dict[str, float]):
    import pandas as pd

    return pd.DataFrame([[features[n] for n in FEATURE_NAMES]], columns=FEATURE_NAMES)


def _load_model(model_path: Path):
    if not model_path.exists():
        return None
    try:
        import joblib

        return joblib.load(model_path)
    except Exception:
        return None


def _load_meta(meta_path: Path) -> dict[str, Any]:
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# Fixed logistic-style coefficients on normalized raw features (fallback only).
# Deterministic; not random. Tuned for interpretable demo behavior.
_FALLBACK_COEFS = {
    "cgpa": 0.135,
    "attendance": 0.0055,
    "backlogs": -0.35,
    "skill_count": 0.08,
    "avg_skill_level": 0.22,
    "project_count": 0.22,
    "internship_count": 0.45,
    "certification_count": 0.18,
    "hackathon_count": 0.15,
}
_FALLBACK_INTERCEPT = -2.35

# Thresholds used to classify a raw feature as a strength vs gap.
_STRENGTH_THRESHOLDS = {
    "cgpa": 7.0,
    "attendance": 75.0,
    "backlogs": 0.0,  # strength when backlogs <= 0 (special-cased below)
    "skill_count": 6.0,
    "avg_skill_level": 3.0,
    "project_count": 2.0,
    "internship_count": 1.0,
    "certification_count": 1.0,
    "hackathon_count": 1.0,
}


def _sigmoid(z: float) -> float:
    z = max(-20.0, min(20.0, z))
    return 1.0 / (1.0 + float(np.exp(-z)))


def _predict_fallback(features: dict[str, float]) -> tuple[float, dict[str, float]]:
    z = _FALLBACK_INTERCEPT
    contributions: dict[str, float] = {}
    for name in FEATURE_NAMES:
        c = _FALLBACK_COEFS[name] * features[name]
        contributions[name] = c
        z += c
    return _sigmoid(z), contributions


def _predict_with_model(model, features: dict[str, float]) -> tuple[float, dict[str, float]]:
    X = _vector_array(features)
    if hasattr(model, "predict_proba"):
        proba = float(model.predict_proba(X)[0][1])
    elif hasattr(model, "decision_function"):
        proba = _sigmoid(float(model.decision_function(X)[0]))
    else:
        pred = float(model.predict(X)[0])
        proba = _clamp01(pred)

    contributions: dict[str, float] = {}
    est = model
    if hasattr(model, "named_steps"):
        est = model.named_steps.get("clf", model.steps[-1][1])

    if hasattr(est, "feature_importances_"):
        imps = np.asarray(est.feature_importances_, dtype=float)
        for i, name in enumerate(FEATURE_NAMES):
            if i < len(imps):
                contributions[name] = float(imps[i]) * float(features[name])
    elif hasattr(est, "coef_"):
        coefs = np.asarray(est.coef_, dtype=float).ravel()
        for i, name in enumerate(FEATURE_NAMES):
            if i < len(coefs):
                contributions[name] = float(coefs[i]) * float(features[name])
    else:
        for name in FEATURE_NAMES:
            contributions[name] = features[name] * _FALLBACK_COEFS[name]
    return proba, contributions


def _factor_labels() -> dict[str, str]:
    return {
        "cgpa": "Academic CGPA",
        "attendance": "Attendance",
        "backlogs": "Backlogs",
        "skill_count": "Breadth of skills",
        "avg_skill_level": "Skill proficiency",
        "project_count": "Project portfolio",
        "internship_count": "Internship experience",
        "certification_count": "Certifications",
        "hackathon_count": "Hackathon participation",
    }


def _is_strength(name: str, feat: float) -> bool:
    if name == "backlogs":
        return feat <= 0
    return feat >= _STRENGTH_THRESHOLDS.get(name, 0.0)


def _split_factors(
    contributions: dict[str, float], features: dict[str, float]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    labels = _factor_labels()
    positive: list[dict[str, Any]] = []
    negative: list[dict[str, Any]] = []
    ranked = sorted(contributions.items(), key=lambda kv: abs(kv[1]), reverse=True)
    for name, contrib in ranked:
        feat = features.get(name, 0.0)
        item = {
            "feature": name,
            "label": labels.get(name, name),
            "value": round(feat, 4),
            "contribution": round(float(contrib), 4),
        }
        if _is_strength(name, feat):
            positive.append(item)
        else:
            negative.append(item)
    return positive, negative


def predict_placement(profile: StudentProfile) -> dict[str, Any]:
    """
    Return placement prediction dict:
    probability, readiness, factors_positive, factors_negative, model_meta.
    """
    features = build_feature_vector(profile)
    model_path = Path(current_app.config.get("ML_MODEL_PATH", ""))
    meta_path = Path(current_app.config.get("ML_META_PATH", ""))
    model = _load_model(model_path) if model_path else None
    file_meta = _load_meta(meta_path) if meta_path else {}

    if model is not None:
        probability, contributions = _predict_with_model(model, features)
        source = "joblib_model"
        model_name = type(model).__name__
    else:
        probability, contributions = _predict_fallback(features)
        source = "deterministic_logistic_fallback"
        model_name = "FallbackLogistic"

    readiness_parts = compute_all_readiness(profile)
    readiness = overall_readiness(profile)
    positive, negative = _split_factors(contributions, features)

    model_meta = {
        "source": source,
        "model_name": model_name,
        "feature_names": FEATURE_NAMES,
        "features": {k: round(v, 4) for k, v in features.items()},
        "readiness_components": readiness_parts,
        "model_path_exists": bool(model_path and model_path.exists()),
        "file_meta": file_meta,
        "synthetic_ml_disclaimer": SYNTHETIC_ML_DISCLAIMER,
    }

    return {
        "probability": round(float(probability), 4),
        "readiness": round(float(readiness), 2),
        "factors_positive": positive,
        "factors_negative": negative,
        "model_meta": model_meta,
    }
