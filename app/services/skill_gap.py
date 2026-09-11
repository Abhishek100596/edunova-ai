"""Skill gap analysis between a student and a target career role."""

from __future__ import annotations

from typing import Any

from app.extensions import db
from app.models.profile import StudentProfile
from app.models.skills import CareerRole, RoleSkill, StudentSkill
from app.services.skill_confidence import compute_skill_confidence


def _level_label(have: int, required: int) -> str:
    if have <= 0:
        return "not_yet_evidenced"
    if have < required:
        return "below_required"
    if have == required:
        return "meets"
    return "exceeds"


def _importance_band(importance: float) -> str:
    if importance >= 1.25:
        return "core"
    if importance >= 1.0:
        return "important"
    if importance >= 0.75:
        return "supporting"
    return "nice_to_have"


def _priority_label(importance: float, gap: int) -> str:
    weighted = importance * max(gap, 0)
    if weighted >= 3.0 or (importance >= 1.25 and gap >= 2):
        return "Critical"
    if weighted >= 1.5 or (importance >= 1.0 and gap >= 2):
        return "High"
    if gap >= 1:
        return "Medium"
    return "Low"


def analyze_skill_gaps(
    profile: StudentProfile, role: CareerRole
) -> dict[str, Any]:
    """
    Compare StudentSkill levels to RoleSkill requirements.

    Returns gaps with gap levels (not_yet_evidenced / below_required / meets / exceeds).
    Absent skills are labelled "not yet evidenced" — never accused as proven absence.
    """
    student_levels = {
        int(s.skill_id): max(1, min(5, int(s.level or 1)))
        for s in StudentSkill.query.filter_by(student_id=profile.id).all()
    }
    requirements = RoleSkill.query.filter_by(role_id=role.id).all()

    gaps: list[dict[str, Any]] = []
    met: list[dict[str, Any]] = []
    total_gap_points = 0
    total_required_points = 0
    weighted_gap = 0.0
    weighted_required = 0.0

    for req in requirements:
        required = max(1, min(5, int(req.required_level or 1)))
        have = student_levels.get(int(req.skill_id), 0)
        skill_name = req.skill.name if req.skill else f"skill#{req.skill_id}"
        gap = max(0, required - have)
        status = _level_label(have, required)
        importance = float(req.importance if req.importance is not None else 1.0)
        total_required_points += required
        total_gap_points += gap
        weighted_required += required * importance
        weighted_gap += gap * importance

        entry = {
            "skill_id": req.skill_id,
            "skill_name": skill_name,
            "category": req.skill.category if req.skill else None,
            "current_level": have,
            "required_level": required,
            "gap_level": gap,
            "importance": importance,
            "importance_band": _importance_band(importance),
            "priority": _priority_label(importance, gap),
            "status": status,
            "evidence_note": (
                "Not yet evidenced on profile"
                if have <= 0
                else "Self-reported level on profile"
            ),
        }
        if gap > 0:
            gaps.append(entry)
        else:
            met.append(entry)

    gaps.sort(key=lambda g: (-g["importance"], -g["gap_level"], g["skill_name"]))
    met.sort(key=lambda m: (-m["importance"], m["skill_name"]))

    coverage = 0.0
    if total_required_points > 0:
        coverage = round(
            ((total_required_points - total_gap_points) / total_required_points) * 100.0,
            2,
        )
    weighted_coverage = 0.0
    if weighted_required > 0:
        weighted_coverage = round(
            ((weighted_required - weighted_gap) / weighted_required) * 100.0, 2
        )

    return {
        "role_id": role.id,
        "role_name": role.name,
        "student_id": profile.id,
        "coverage_pct": coverage,
        "weighted_coverage_pct": weighted_coverage,
        "gaps": gaps,
        "met": met,
        "gap_count": len(gaps),
        "met_count": len(met),
        "disclaimer": (
            "Gaps reflect catalog requirements vs profile evidence — "
            "not proven skill absence or hiring outcomes."
        ),
    }


def skill_gap_matrix(
    profile: StudentProfile, role: CareerRole
) -> dict[str, Any]:
    """Full Skill | Required | Current | Gap | Importance | Evidence | Priority matrix."""
    base = analyze_skill_gaps(profile, role)
    conf_map = {
        r["skill_id"]: r for r in compute_skill_confidence(profile)
    }
    matrix: list[dict[str, Any]] = []
    for row in base["gaps"] + base["met"]:
        conf = conf_map.get(row["skill_id"])
        matrix.append(
            {
                **row,
                "confidence": conf["confidence"] if conf else None,
                "confidence_label": conf["label"] if conf else (
                    "Not evidenced" if row["current_level"] <= 0 else "Self-reported"
                ),
                "evidence": (
                    conf["evidence_bits"]
                    if conf
                    else [row.get("evidence_note") or "Not yet evidenced"]
                ),
            }
        )
    priority_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    matrix.sort(
        key=lambda r: (
            priority_order.get(r.get("priority", "Low"), 9),
            -float(r.get("importance", 0)),
            -int(r.get("gap_level", 0)),
            r.get("skill_name", ""),
        )
    )
    return {
        "role_id": role.id,
        "role_name": role.name,
        "coverage_pct": base["coverage_pct"],
        "weighted_coverage_pct": base["weighted_coverage_pct"],
        "matrix": matrix,
        "disclaimer": base["disclaimer"],
    }


def gaps_for_role_id(profile: StudentProfile, role_id: int) -> dict[str, Any]:
    role = db.session.get(CareerRole, role_id)
    if role is None:
        raise ValueError(f"Career role id={role_id} not found.")
    return analyze_skill_gaps(profile, role)
