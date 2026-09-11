"""Rule-based career role matching against RoleSkill vs StudentSkill."""

from __future__ import annotations

from typing import Any

from app.models.profile import StudentProfile
from app.models.skills import CareerRole, RoleSkill, StudentSkill


def _student_skill_map(profile: StudentProfile) -> dict[int, int]:
    links = StudentSkill.query.filter_by(student_id=profile.id).all()
    return {
        int(s.skill_id): max(1, min(5, int(s.level or 1))) for s in links
    }


def score_role(
    role: CareerRole, student_levels: dict[int, int]
) -> dict[str, Any]:
    requirements = RoleSkill.query.filter_by(role_id=role.id).all()
    if not requirements:
        return {
            "role_id": role.id,
            "role_name": role.name,
            "category": role.category,
            "description": role.description,
            "match_pct": 0.0,
            "strengths": [],
            "gaps": [],
            "weighted_score": 0.0,
            "max_score": 0.0,
        }

    strengths: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    earned = 0.0
    maximum = 0.0

    for req in requirements:
        importance = float(req.importance if req.importance is not None else 1.0)
        required = max(1, min(5, int(req.required_level or 1)))
        maximum += importance * required
        have = student_levels.get(int(req.skill_id), 0)
        skill_name = req.skill.name if req.skill else f"skill#{req.skill_id}"

        if have >= required:
            earned += importance * required
            strengths.append(
                {
                    "skill_id": req.skill_id,
                    "skill_name": skill_name,
                    "level": have,
                    "required_level": required,
                    "importance": importance,
                }
            )
        elif have > 0:
            earned += importance * have
            gaps.append(
                {
                    "skill_id": req.skill_id,
                    "skill_name": skill_name,
                    "level": have,
                    "required_level": required,
                    "gap": required - have,
                    "importance": importance,
                    "status": "partial",
                }
            )
        else:
            gaps.append(
                {
                    "skill_id": req.skill_id,
                    "skill_name": skill_name,
                    "level": 0,
                    "required_level": required,
                    "gap": required,
                    "importance": importance,
                    "status": "missing",
                }
            )

    match_pct = round((earned / maximum) * 100.0, 2) if maximum > 0 else 0.0
    strengths.sort(key=lambda x: (-x["importance"], -x["level"]))
    gaps.sort(key=lambda x: (-x["importance"], -x["gap"]))

    return {
        "role_id": role.id,
        "role_name": role.name,
        "category": role.category,
        "description": role.description,
        "match_pct": match_pct,
        "strengths": strengths,
        "gaps": gaps,
        "weighted_score": round(earned, 4),
        "max_score": round(maximum, 4),
    }


def match_roles(
    profile: StudentProfile, *, limit: int | None = None
) -> list[dict[str, Any]]:
    """Return ranked role matches with match_pct, strengths, and gaps."""
    student_levels = _student_skill_map(profile)
    roles = CareerRole.query.order_by(CareerRole.name.asc()).all()
    ranked = [score_role(role, student_levels) for role in roles]
    ranked.sort(key=lambda r: (-r["match_pct"], r["role_name"]))
    if limit is not None:
        return ranked[: max(0, int(limit))]
    return ranked
