"""Career Switch Intelligence — transferable skills and staged transition plans."""

from __future__ import annotations

from typing import Any

from app.extensions import db
from app.models.profile import StudentProfile
from app.models.skills import CareerRole, RoleSkill, StudentSkill
from app.services.skill_gap import analyze_skill_gaps, skill_gap_matrix


DISCLAIMER = (
    "Career-switch analysis is a compatibility estimate based on catalog skill "
    "requirements — not a hiring or promotion guarantee."
)


def analyze_career_switch(
    profile: StudentProfile,
    *,
    current_role_id: int | None,
    target_role_id: int,
    current_role_label: str | None = None,
) -> dict[str, Any]:
    target = db.session.get(CareerRole, target_role_id)
    if target is None:
        return {"error": "target_role_not_found", "disclaimer": DISCLAIMER}

    current: CareerRole | None = None
    if current_role_id:
        current = db.session.get(CareerRole, current_role_id)

    student_levels = {
        int(s.skill_id): max(1, min(5, int(s.level or 1)))
        for s in StudentSkill.query.filter_by(student_id=profile.id).all()
    }
    student_names = {
        int(s.skill_id): (s.skill.name if s.skill else f"skill#{s.skill_id}")
        for s in StudentSkill.query.filter_by(student_id=profile.id).all()
    }

    target_reqs = RoleSkill.query.filter_by(role_id=target.id).all()
    current_req_ids: set[int] = set()
    if current is not None:
        current_req_ids = {
            int(r.skill_id) for r in RoleSkill.query.filter_by(role_id=current.id).all()
        }

    transferable: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for req in target_reqs:
        sid = int(req.skill_id)
        name = req.skill.name if req.skill else f"skill#{sid}"
        required = max(1, min(5, int(req.required_level or 1)))
        have = student_levels.get(sid, 0)
        importance = float(req.importance if req.importance is not None else 1.0)
        row = {
            "skill_id": sid,
            "skill_name": name,
            "required_level": required,
            "current_level": have,
            "importance": importance,
            "on_current_role_catalog": sid in current_req_ids,
        }
        if have >= required and have > 0:
            transferable.append(row)
        elif have > 0 and have < required:
            transferable.append({**row, "note": "partially transferable — deepen level"})
            missing.append(row)
        else:
            missing.append(row)

    transferable.sort(key=lambda r: (-r["importance"], r["skill_name"]))
    missing.sort(key=lambda r: (-r["importance"], -r["required_level"], r["skill_name"]))

    gaps = analyze_skill_gaps(profile, target)
    matrix = skill_gap_matrix(profile, target)

    stages = [
        {
            "stage": 1,
            "title": "Foundations for target role",
            "focus": [m["skill_name"] for m in missing[:3]],
            "why": "Close the highest-importance skill gaps first.",
        },
        {
            "stage": 2,
            "title": "Portfolio evidence",
            "focus": ["2 targeted projects using missing stack skills"],
            "why": "Projects convert self-reported skills into evidenced skills.",
        },
        {
            "stage": 3,
            "title": "Applied depth",
            "focus": ["Deploy or document one end-to-end workflow"],
            "why": "Interviewers ask for production-shaped evidence.",
        },
        {
            "stage": 4,
            "title": "Interview preparation",
            "focus": ["Role-specific technical + behavioral practice"],
            "why": "Convert learning into interview-ready explanations.",
        },
    ]

    current_label = (
        current.name
        if current is not None
        else (current_role_label or "Current profile (no catalog role)")
    )

    return {
        "current_role": {
            "id": current.id if current else None,
            "name": current_label,
        },
        "target_role": {"id": target.id, "name": target.name, "category": target.category},
        "transferable_skills": transferable,
        "missing_skills": missing,
        "coverage_pct": gaps.get("coverage_pct"),
        "skill_matrix": matrix.get("matrix", []),
        "student_skill_count": len(student_names),
        "transition_plan": stages,
        "risk_factors": _risk_factors(missing, transferable),
        "disclaimer": DISCLAIMER,
    }


def _risk_factors(
    missing: list[dict[str, Any]], transferable: list[dict[str, Any]]
) -> list[str]:
    risks: list[str] = []
    critical = [m for m in missing if m.get("importance", 1) >= 1.2 and m.get("current_level", 0) <= 0]
    if critical:
        risks.append(
            "Critical catalog skills have no evidenced level yet: "
            + ", ".join(m["skill_name"] for m in critical[:5])
        )
    if len(transferable) < 2:
        risks.append("Few strongly transferable skills relative to the target catalog.")
    if len(missing) >= 5:
        risks.append("Large skill surface area — prefer an intermediate adjacent role first.")
    if not risks:
        risks.append("No major catalog risk flags — still validate against live job descriptions.")
    return risks
