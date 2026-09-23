"""Personalized learning planner built on skill gaps + optional AI narrative."""

from __future__ import annotations

from typing import Any

from app.models.profile import StudentProfile
from app.models.skills import CareerRole
from app.services.career import match_roles
from app.services.skill_gap import analyze_skill_gaps


def _pick_role(profile: StudentProfile, role: CareerRole | None) -> CareerRole | None:
    if role is not None:
        return role
    matches = match_roles(profile, limit=1)
    if not matches:
        return None
    return CareerRole.query.get(matches[0]["role_id"])


def build_learning_plan(
    profile: StudentProfile,
    role: CareerRole | None = None,
    *,
    weeks: int = 4,
) -> dict[str, Any]:
    """
    Deterministic weekly plan from skill gaps.

    Does not invent student achievements. Optional AI narrative is added by the route.
    """
    weeks = max(2, min(8, int(weeks)))
    target = _pick_role(profile, role)
    if target is None:
        return {
            "ok": False,
            "goal": "Choose a target career role to generate a learning plan.",
            "weeks": [],
            "gaps": [],
            "disclaimer": "Educational plan only — not a placement guarantee.",
        }

    analysis = analyze_skill_gaps(profile, target)
    gaps = list(analysis.get("gaps") or analysis.get("missing") or [])[:12]
    gap_names: list[str] = []
    for g in gaps:
        if isinstance(g, dict):
            gap_names.append(str(g.get("skill_name") or g.get("name") or g))
        else:
            gap_names.append(str(g))

    known = [
        s.skill.name
        for s in (profile.skills or [])
        if getattr(s, "skill", None) and s.skill.name
    ]
    # Fallback if relationship not loaded
    if not known:
        from app.models.skills import StudentSkill

        known = [
            link.skill.name
            for link in StudentSkill.query.filter_by(student_id=profile.id).all()
            if link.skill and link.skill.name
        ]

    weekly: list[dict[str, Any]] = []
    focus_skills = gap_names or ["core fundamentals for your target role"]
    for w in range(1, weeks + 1):
        skill = focus_skills[(w - 1) % len(focus_skills)]
        phase = (
            "Foundation"
            if w == 1
            else ("Practice" if w < weeks else "Interview & portfolio")
        )
        weekly.append(
            {
                "week": w,
                "theme": phase,
                "focus_skill": skill,
                "estimated_hours": 8 if w < weeks else 10,
                "daily_tasks": [
                    f"Study {skill} concepts for 45–60 minutes",
                    f"Complete one hands-on exercise related to {skill}",
                    "Log what you practiced in EduNova projects or notes",
                ],
                "practice": f"Build a small exercise that demonstrates {skill}",
                "checkpoint": f"Explain {skill} out loud in 3 minutes without notes",
                "interview_questions": [
                    f"What is {skill} and when would you use it?",
                    f"Describe a small task where {skill} improved a result.",
                ],
            }
        )

    mini_project = (
        f"Build a small portfolio piece for {target.name} that uses "
        f"{', '.join(focus_skills[:3])}."
        if focus_skills
        else f"Build a small portfolio piece aligned to {target.name}."
    )

    return {
        "ok": True,
        "goal": f"Prepare for {target.name} over {weeks} weeks",
        "role_id": target.id,
        "role_name": target.name,
        "current_skills": known[:20],
        "gaps": gap_names,
        "prerequisites": known[:6] or ["Complete onboarding and add your current skills"],
        "weeks": weekly,
        "mini_project": mini_project,
        "revision_checkpoints": [
            f"End of week {i}: review notes and redo one exercise"
            for i in range(1, weeks + 1)
        ],
        "disclaimer": (
            "Educational learning plan derived from catalog skill gaps — "
            "not a hiring or placement guarantee."
        ),
    }
