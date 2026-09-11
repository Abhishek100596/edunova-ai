"""What-if scenario simulations — never mutate the database."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.models.profile import StudentProfile
from app.models.skills import Skill, StudentSkill
from app.services.career import match_roles
from app.services.placement import FEATURE_NAMES, build_feature_vector, _predict_fallback
from app.utils.readiness import compute_all_readiness, overall_readiness


SCENARIO_LABEL = "scenario simulation"


def _base_snapshot(profile: StudentProfile) -> dict[str, Any]:
    features = build_feature_vector(profile)
    readiness = compute_all_readiness(profile)
    overall = overall_readiness(profile)
    proba, _ = _predict_fallback(features)
    top = match_roles(profile, limit=3)
    return {
        "features": features,
        "readiness_components": readiness,
        "overall_readiness": overall,
        "placement_probability_estimate": round(float(proba), 4),
        "top_roles": [
            {"role_name": r["role_name"], "match_pct": r["match_pct"]} for r in top
        ],
    }


def _recompute_from_features(
    features: dict[str, float],
    *,
    readiness_override: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Estimate readiness-like scores from a cloned feature vector only."""
    feats = {k: float(features.get(k, 0.0)) for k in FEATURE_NAMES}
    cgpa = feats["cgpa"]
    attendance = feats["attendance"]
    backlogs = feats["backlogs"]
    skill_count = feats["skill_count"]
    avg_level = feats["avg_skill_level"]
    project_count = int(feats["project_count"])
    internship_count = int(feats["internship_count"])
    cert_count = int(feats["certification_count"])

    # Mirror readiness.py formulas without DB access.
    cgpa_10 = cgpa
    cgpa_score = max(0.0, min(100.0, (cgpa_10 / 10.0) * 100.0))
    attendance_score = max(0.0, min(100.0, attendance))
    backlog_penalty = min(40.0, backlogs * 10.0)
    academic = round(
        0.45 * cgpa_score
        + 0.25 * attendance_score
        + 0.20 * 50.0
        + 0.10 * (100.0 - backlog_penalty),
        2,
    )
    if skill_count <= 0:
        skill = 0.0
    else:
        count_factor = min(1.0, skill_count / 12.0)
        skill = round((avg_level / 5.0) * 70.0 + count_factor * 30.0, 2)
        skill = max(0.0, min(100.0, skill))

    thresholds = [(0, 0.0), (1, 40.0), (2, 65.0), (3, 80.0), (4, 95.0)]
    project = 100.0
    for n, s in thresholds:
        if project_count <= n:
            project = s
            break
    if project_count > 4:
        project = 100.0

    if internship_count <= 0:
        experience = 0.0
    elif internship_count == 1:
        experience = 55.0
    elif internship_count == 2:
        experience = 80.0
    else:
        experience = 100.0

    if cert_count <= 0:
        certification = 0.0
    elif cert_count == 1:
        certification = 50.0
    elif cert_count == 2:
        certification = 75.0
    else:
        certification = 100.0

    components = readiness_override or {
        "academic": academic,
        "skill": skill,
        "project": round(project, 2),
        "experience": experience,
        "certification": certification,
        "interview": 0.0,  # unchanged in feature-only sims unless provided
    }
    weights = {
        "academic": 0.25,
        "skill": 0.25,
        "project": 0.15,
        "experience": 0.15,
        "certification": 0.10,
        "interview": 0.10,
    }
    total_w = sum(weights.values())
    overall = round(
        sum(components[k] * weights[k] for k in components) / total_w, 2
    )
    proba, _ = _predict_fallback(feats)
    return {
        "features": {k: round(v, 4) for k, v in feats.items()},
        "readiness_components": components,
        "overall_readiness": overall,
        "placement_probability_estimate": round(float(proba), 4),
    }


def simulate_skill_level_change(
    profile: StudentProfile, skill_name: str, new_level: int
) -> dict[str, Any]:
    """
    Clone feature vector / recompute readiness-like estimates for a hypothetical
    skill level change. Does not mutate the database.
    """
    baseline = _base_snapshot(profile)
    features = deepcopy(baseline["features"])
    new_level = max(1, min(5, int(new_level)))
    name = (skill_name or "").strip()

    links = StudentSkill.query.filter_by(student_id=profile.id).all()
    levels: list[int] = []
    found = False
    for link in links:
        sk_name = link.skill.name if link.skill else ""
        if sk_name.lower() == name.lower():
            levels.append(new_level)
            found = True
        else:
            levels.append(max(1, min(5, int(link.level or 1))))

    if not found:
        # Hypothetical new skill on the profile vector only
        skill_row = Skill.query.filter(Skill.name.ilike(name)).first()
        levels.append(new_level)
        features["skill_count"] = float(len(levels))
        note = (
            f"Skill {name!r} not on profile — simulated as added "
            f"(skill_id={skill_row.id if skill_row else None})."
        )
    else:
        features["skill_count"] = float(len(levels))
        note = f"Simulated changing {name!r} to level {new_level}."

    features["avg_skill_level"] = (
        round(sum(levels) / len(levels), 2) if levels else 0.0
    )

    scenario = _recompute_from_features(features)
    scenario["readiness_components"]["interview"] = baseline["readiness_components"][
        "interview"
    ]
    # Recompute overall with interview preserved
    w = {
        "academic": 0.25,
        "skill": 0.25,
        "project": 0.15,
        "experience": 0.15,
        "certification": 0.10,
        "interview": 0.10,
    }
    parts = scenario["readiness_components"]
    scenario["overall_readiness"] = round(
        sum(parts[k] * w[k] for k in w) / sum(w.values()), 2
    )

    return {
        "label": SCENARIO_LABEL,
        "scenario": "skill_level_change",
        "skill_name": name,
        "new_level": new_level,
        "note": note,
        "baseline": baseline,
        "simulated": scenario,
        "delta_overall_readiness": round(
            scenario["overall_readiness"] - baseline["overall_readiness"], 2
        ),
        "delta_placement_probability": round(
            scenario["placement_probability_estimate"]
            - baseline["placement_probability_estimate"],
            4,
        ),
        "disclaimer": (
            "Scenario simulation only — profile and database were not modified."
        ),
    }


def simulate_extra_projects(profile: StudentProfile, n: int) -> dict[str, Any]:
    """Simulate adding n projects to the feature vector without DB writes."""
    baseline = _base_snapshot(profile)
    features = deepcopy(baseline["features"])
    n = max(0, int(n))
    features["project_count"] = float(features.get("project_count", 0.0) + n)
    # hackathon heuristic mirrors placement.build_feature_vector lightly
    projects = int(features["project_count"])
    features["hackathon_count"] = float(
        min(5, max(0, int(features.get("hackathon_count", 0)) + (1 if n and projects >= 3 else 0)))
    )

    scenario = _recompute_from_features(features)
    scenario["readiness_components"]["interview"] = baseline["readiness_components"][
        "interview"
    ]
    w = {
        "academic": 0.25,
        "skill": 0.25,
        "project": 0.15,
        "experience": 0.15,
        "certification": 0.10,
        "interview": 0.10,
    }
    parts = scenario["readiness_components"]
    scenario["overall_readiness"] = round(
        sum(parts[k] * w[k] for k in w) / sum(w.values()), 2
    )

    return {
        "label": SCENARIO_LABEL,
        "scenario": "extra_projects",
        "extra_projects": n,
        "note": f"Simulated adding {n} project(s) to the feature vector.",
        "baseline": baseline,
        "simulated": scenario,
        "delta_overall_readiness": round(
            scenario["overall_readiness"] - baseline["overall_readiness"], 2
        ),
        "delta_placement_probability": round(
            scenario["placement_probability_estimate"]
            - baseline["placement_probability_estimate"],
            4,
        ),
        "disclaimer": (
            "Scenario simulation only — profile and database were not modified."
        ),
    }
