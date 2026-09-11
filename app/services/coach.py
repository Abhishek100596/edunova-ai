"""Career coach — builds profile context and calls the AI provider."""

from __future__ import annotations

import json
from typing import Any

from flask import current_app

from app.ai.provider import LocalProvider, get_ai_provider
from app.extensions import db
from app.models.analytics import AIConversation
from app.models.experience import Certification, Internship, Project
from app.models.profile import StudentProfile
from app.models.skills import StudentSkill
from app.models.user import User


def _parse_json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, str):
            return [data]
        return [data]
    except json.JSONDecodeError:
        return [part.strip() for part in raw.split(",") if part.strip()]


def build_student_context(profile: StudentProfile) -> dict[str, Any]:
    """Assemble factual context from DB — skills only those on record."""
    user: User | None = profile.user
    skill_rows = (
        StudentSkill.query.filter_by(student_id=profile.id)
        .order_by(StudentSkill.level.desc())
        .all()
    )
    skills = []
    for row in skill_rows:
        name = row.skill.name if row.skill else f"skill#{row.skill_id}"
        skills.append(f"{name} (L{row.level})")

    skill_names_only = [
        (row.skill.name if row.skill else f"skill#{row.skill_id}") for row in skill_rows
    ]

    projects = Project.query.filter_by(student_id=profile.id).all()
    internships = Internship.query.filter_by(student_id=profile.id).all()
    certs = Certification.query.filter_by(student_id=profile.id).all()

    enriched: dict[str, Any] = {}
    try:
        from app.services.personalization import dashboard_intelligence

        dash = dashboard_intelligence(profile)
        enriched = {
            "readiness_overall": dash["readiness"].get("overall"),
            "readiness_components": dash["readiness"].get("components"),
            "top_role": (dash["career_matches"][0] if dash["career_matches"] else None),
            "roadmap_progress": dash["roadmap"].get("progress_pct"),
            "interview_avg": dash["interview"].get("average_score"),
            "recommended_actions": [a["title"] for a in dash["actions"][:3]],
        }
    except Exception:  # noqa: BLE001
        enriched = {}

    return {
        "name": (user.name if user else "") or "",
        "email": (user.email if user else "") or "",
        "college": profile.college,
        "degree": profile.degree,
        "branch": profile.branch,
        "graduation_year": profile.graduation_year,
        "location": profile.location,
        "cgpa": profile.cgpa,
        "attendance": profile.attendance,
        "backlogs": profile.backlogs,
        "skills": skills,
        "skill_names": skill_names_only,
        "preferred_roles": _parse_json_list(profile.preferred_roles),
        "preferred_industries": _parse_json_list(profile.preferred_industries),
        "target_companies": _parse_json_list(profile.target_companies),
        "preferred_location": profile.preferred_location,
        "higher_studies": profile.higher_studies,
        "project_count": len(projects),
        "project_titles": [p.title for p in projects],
        "internship_count": len(internships),
        "internship_companies": [i.company for i in internships],
        "certification_count": len(certs),
        "certification_names": [c.name for c in certs],
        **enriched,
    }


_SYSTEM_PROMPT = (
    "You are EDUNOVA AI, a career intelligence coach for students. "
    "Use only the provided student context. "
    "NEVER invent skills, projects, internships, certifications, or grades "
    "the student does not have. If information is missing, say so and ask "
    "the student to update their profile. "
    "Distinguish profile facts, derived estimates, and recommendations. "
    "Scores are estimates, not hiring guarantees."
)


def _local_smart_reply(message: str, context: dict[str, Any]) -> str:
    """Deterministic coaching grounded in profile + personalization signals."""
    msg = (message or "").lower()
    skills = context.get("skill_names") or []
    readiness = context.get("readiness_overall")
    top = context.get("top_role") or {}
    actions = context.get("recommended_actions") or []
    lines = [
        "[DEMO — LocalProvider] Deterministic coaching from your stored profile "
        "(not a live LLM).",
        f"Profile: {context.get('name') or 'Student'} · "
        f"{context.get('degree') or '—'} {context.get('branch') or ''}".strip(),
        f"Skills on file: {', '.join(skills[:12]) or '(none)'}",
    ]
    if readiness is not None:
        lines.append(f"Current readiness estimate: {readiness}/100")
        comps = context.get("readiness_components") or {}
        if comps:
            parts = ", ".join(f"{k}={v}" for k, v in list(comps.items())[:6])
            lines.append(f"Factor breakdown: {parts}")
    if top:
        lines.append(
            f"Top catalog career match: {top.get('role_name')} "
            f"({top.get('match_pct')}%)."
        )
        gaps = top.get("gaps") or []
        if gaps:
            g0 = gaps[0]
            name = g0.get("skill_name") if isinstance(g0, dict) else str(g0)
            lines.append(f"Largest gap for that role: {name}")

    if any(k in msg for k in ("ready", "readiness", "why")):
        lines.append(
            "Readiness is a weighted estimate from academics, skills, projects, "
            "experience, certifications, and interview history — not a placement promise."
        )
    elif any(k in msg for k in ("learn", "next", "gap", "roadmap")):
        if actions:
            lines.append("Suggested next actions from your data:")
            lines.extend(f"• {a}" for a in actions)
        else:
            lines.append(
                "Add a target role and skills so EDUNOVA can prioritize learning next."
            )
    elif any(k in msg for k in ("company", "target", "microsoft", "google", "tcs")):
        targets = context.get("target_companies") or []
        lines.append(
            "Company advice uses your target list and catalog compatibility estimates only."
        )
        if targets:
            lines.append("Targets on profile: " + ", ".join(str(t) for t in targets[:8]))
        lines.append(
            "Improve company fit by closing role-critical skill gaps and evidencing them in projects."
        )
    elif any(k in msg for k in ("resume",)):
        lines.append(
            "Resume tip: quantify outcomes on projects already listed; never invent experience."
        )
    elif any(k in msg for k in ("interview",)):
        lines.append(
            "Interview tip: practice role-specific SQL/Python/project questions and review weak topics."
        )
    else:
        lines.append(
            "Ask about readiness, skill gaps, target companies, resume, or interview prep "
            "for more specific guidance."
        )
    lines.append(f"Your question: {(message or '').strip()[:400]}")
    return "\n".join(lines)


def ask_coach(
    profile: StudentProfile,
    message: str,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    """Call the configured AI provider with grounded student context."""
    context = build_student_context(profile)
    grounded_message = (
        f"{message.strip()}\n\n"
        "[Constraint] Only reference skills from this list: "
        f"{', '.join(context['skill_names']) or '(none on file)'}."
    )

    provider_name = "local-demo"
    try:
        provider = get_ai_provider(current_app.config)
        provider_name = getattr(provider, "name", provider_name)
        if provider_name in {"local", "local-demo", "demo"}:
            reply = _local_smart_reply(message, context)
        else:
            reply = provider.complete(
                grounded_message,
                system=_SYSTEM_PROMPT,
                context=context,
            )
    except Exception as exc:  # noqa: BLE001 — never crash coach UX
        provider_name = "local-fallback"
        reply = _local_smart_reply(
            message + f"\n(Note: cloud provider unavailable — {exc})",
            context,
        )

    if persist:
        db.session.add(
            AIConversation(
                student_id=profile.id,
                role="user",
                message=message,
                provider=provider_name,
            )
        )
        db.session.add(
            AIConversation(
                student_id=profile.id,
                role="assistant",
                message=reply,
                provider=provider_name,
                meta=json.dumps(
                    {
                        "skill_names": context["skill_names"],
                        "project_count": context["project_count"],
                        "readiness_overall": context.get("readiness_overall"),
                    }
                ),
            )
        )
        db.session.commit()

    return {
        "provider": provider_name,
        "reply": reply,
        "context_skills": context["skill_names"],
    }


def clear_conversation(profile: StudentProfile) -> int:
    rows = AIConversation.query.filter_by(student_id=profile.id).all()
    count = len(rows)
    for row in rows:
        db.session.delete(row)
    db.session.commit()
    return count
