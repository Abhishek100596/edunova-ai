"""Career coach — profile context + conversation memory + AI provider."""

from __future__ import annotations

import json
import re
from typing import Any

from flask import current_app

from app.ai.provider import get_ai_provider
from app.extensions import db
from app.models.analytics import AIConversation
from app.models.experience import Certification, Internship, Project
from app.models.profile import StudentProfile
from app.models.skills import StudentSkill
from app.models.user import User

HISTORY_WINDOW = 16


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

    project_summaries: list[str] = []
    for p in projects[:8]:
        bit = p.title
        if p.tech_stack:
            bit += f" [{p.tech_stack}]"
        if getattr(p, "analysis_json", None):
            try:
                analysis = json.loads(p.analysis_json)
                found = (analysis.get("found_in_repository") or {}).get("languages") or []
                if found:
                    bit += f" (langs: {', '.join(found[:4])})"
            except (json.JSONDecodeError, TypeError):
                pass
        project_summaries.append(bit)

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
        "project_summaries": project_summaries,
        "internship_count": len(internships),
        "internship_companies": [i.company for i in internships],
        "certification_count": len(certs),
        "certification_names": [c.name for c in certs],
        **enriched,
    }


def recent_conversation(
    profile: StudentProfile, *, limit: int = HISTORY_WINDOW
) -> list[dict[str, str]]:
    rows = (
        AIConversation.query.filter_by(student_id=profile.id)
        .order_by(AIConversation.created_at.desc())
        .limit(limit)
        .all()
    )
    rows = list(reversed(rows))
    return [
        {"role": r.role, "message": r.message, "provider": r.provider or ""}
        for r in rows
    ]


def _last_assistant_focus(history: list[dict[str, str]], context: dict[str, Any]) -> str | None:
    """Extract the most recently emphasized skill/topic from assistant replies."""
    skills = [s.lower() for s in (context.get("skill_names") or [])]
    top = context.get("top_role") or {}
    gap0 = None
    gaps = top.get("gaps") or []
    if gaps:
        g0 = gaps[0]
        gap0 = (g0.get("skill_name") if isinstance(g0, dict) else str(g0)).lower()

    for item in reversed(history):
        if item.get("role") != "assistant":
            continue
        text = (item.get("message") or "").lower()
        # Prefer explicit "learn X" patterns
        m = re.search(
            r"(?:learn|focus on|practice|build|study)\s+([a-z0-9+#./ ]{2,40})",
            text,
        )
        if m:
            candidate = m.group(1).strip(" .,:;")
            if candidate:
                return candidate.title()
        for skill in skills:
            if skill and skill in text:
                return skill.title()
        if gap0 and gap0 in text:
            return gap0.title()
    if gap0:
        return gap0.title()
    if skills:
        return skills[0].title()
    return None


_SYSTEM_PROMPT = (
    "You are EDUNOVA AI, a career intelligence coach for students. "
    "Use only the provided student context and recent conversation. "
    "Answer the student's CURRENT question directly. "
    "If they ask a follow-up (why, how, plan, project), continue from the prior topic. "
    "NEVER invent skills, projects, internships, certifications, or grades "
    "the student does not have. If information is missing, say so and ask "
    "the student to update their profile. "
    "Distinguish profile facts, derived estimates, and recommendations. "
    "Scores are estimates, not hiring guarantees. "
    "Do not repeat a previous answer verbatim; add new, useful detail."
)


def _local_smart_reply(
    message: str,
    context: dict[str, Any],
    history: list[dict[str, str]] | None = None,
) -> str:
    """Contextual deterministic coaching — varies with question + history."""
    history = history or []
    msg = (message or "").strip()
    msg_l = msg.lower()
    skills = context.get("skill_names") or []
    readiness = context.get("readiness_overall")
    top = context.get("top_role") or {}
    actions = context.get("recommended_actions") or []
    focus = _last_assistant_focus(history, context)
    roles = context.get("preferred_roles") or []
    projects = context.get("project_summaries") or context.get("project_titles") or []

    lines = [
        "[Local coach] Guidance grounded in your saved EduNova profile "
        "(cloud provider unavailable or set to local).",
        f"Student: {context.get('name') or 'Student'} · "
        f"{(context.get('degree') or '')} {(context.get('branch') or '')}".strip(),
    ]
    if skills:
        lines.append("Skills on file: " + ", ".join(skills[:12]))
    if readiness is not None:
        lines.append(f"Readiness estimate: {readiness}/100")
    if top:
        lines.append(
            f"Top catalog match: {top.get('role_name')} ({top.get('match_pct')}%)."
        )

    def _gap_skill() -> str | None:
        gaps = top.get("gaps") or []
        if gaps:
            g0 = gaps[0]
            return g0.get("skill_name") if isinstance(g0, dict) else str(g0)
        return focus

    # Follow-ups tied to prior focus
    if any(k in msg_l for k in ("why should i learn", "why that", "why this", "why learn")):
        topic = focus or _gap_skill() or (skills[0] if skills else "a core skill")
        lines.append(
            f"You should learn {topic} next because it closes a documented gap for "
            f"{top.get('role_name') or (roles[0] if roles else 'your target role')} "
            "and strengthens evidence recruiters look for in that track."
        )
        if top.get("gaps"):
            lines.append(
                "Your catalog gap analysis prioritizes skills you do not yet meet at the required level."
            )
        return "\n".join(lines)

    if any(
        k in msg_l
        for k in ("30 day", "30-day", "study plan", "learning plan", "make a plan")
    ):
        topic = focus or _gap_skill() or (skills[0] if skills else "fundamentals")
        lines.extend(
            [
                f"30-day plan focused on {topic}:",
                f"• Days 1–7: Fundamentals of {topic} (concepts + short exercises).",
                f"• Days 8–14: Guided tutorials applying {topic} to a tiny dataset or feature.",
                f"• Days 15–21: Build a small demo that uses {topic} and document results.",
                f"• Days 22–30: Polish README, practice explaining {topic} in interviews, "
                "and mark related roadmap tasks complete in EduNova.",
            ]
        )
        return "\n".join(lines)

    if any(k in msg_l for k in ("what project", "which project", "project should")):
        topic = focus or _gap_skill() or "your strongest skill"
        lines.append(
            f"Build a portfolio project that showcases {topic} end-to-end "
            "(problem → data/code → result → short write-up)."
        )
        if projects:
            lines.append(
                "You already list: "
                + "; ".join(str(p) for p in projects[:4])
                + ". Extend one of these or start a focused new demo around the skill above."
            )
        else:
            lines.append(
                "You have no projects on file yet — add a GitHub repo in Projects so advice can stay concrete."
            )
        return "\n".join(lines)

    if any(k in msg_l for k in ("missing", "skill gap", "skills am i")):
        gaps = top.get("gaps") or []
        if gaps:
            lines.append("Missing / below-target skills for your top catalog role:")
            for g in gaps[:6]:
                name = g.get("skill_name") if isinstance(g, dict) else str(g)
                lines.append(f"• {name}")
        else:
            lines.append(
                "No large gaps were computed yet. Set a preferred role and skills, then regenerate analysis."
            )
        return "\n".join(lines)

    if any(k in msg_l for k in ("learn next", "what should i learn", "improve my skills", "how do i improve")):
        topic = _gap_skill() or (actions[0] if actions else None)
        if topic and isinstance(topic, str) and not topic.lower().startswith("start"):
            lines.append(f"Next learning focus: {topic}.")
            lines.append(
                f"After that, ask “Why should I learn that?” or “Give me a 30 day plan” for a follow-up."
            )
        elif actions:
            lines.append("Suggested next actions from your data:")
            lines.extend(f"• {a}" for a in actions)
        else:
            lines.append(
                "Add a target role and skills so EduNova can prioritize what to learn next."
            )
        return "\n".join(lines)

    if any(k in msg_l for k in ("roadmap", "career path", "become a", "suitable for me")):
        if top:
            lines.append(
                f"A suitable near-term catalog direction is {top.get('role_name')} "
                f"at about {top.get('match_pct')}% current match."
            )
        if roles:
            lines.append("Preferred roles on profile: " + ", ".join(str(r) for r in roles[:5]))
        lines.append(
            "Open Learning Roadmap and generate a plan for that role so progress persists in SQL."
        )
        return "\n".join(lines)

    if any(k in msg_l for k in ("company", "companies should", "target next")):
        targets = context.get("target_companies") or []
        lines.append(
            "Company targeting uses your saved target list and educational compatibility estimates."
        )
        if targets:
            lines.append("Targets on profile: " + ", ".join(str(t) for t in targets[:8]))
        lines.append(
            "Use Company Comparison to see fit percentages and missing skills side by side."
        )
        return "\n".join(lines)

    if "resume" in msg_l:
        lines.append(
            "Resume tip: quantify outcomes on projects already listed; never invent experience."
        )
        if projects:
            lines.append("Project evidence available: " + "; ".join(str(p) for p in projects[:3]))
        return "\n".join(lines)

    if "interview" in msg_l:
        kind = "technical" if "technical" in msg_l else ("HR" if "hr" in msg_l else "behavioral/technical")
        lines.append(
            f"For {kind} interview prep: practice role-specific questions using only skills and projects on your profile."
        )
        lines.append("Use Interview Prep in EduNova to run a scored mock session.")
        return "\n".join(lines)

    if any(k in msg_l for k in ("ready", "readiness", "placement readiness")):
        lines.append(
            "Readiness is a weighted estimate from academics, skills, projects, "
            "experience, certifications, and interview history — not a placement promise."
        )
        comps = context.get("readiness_components") or {}
        if comps:
            parts = ", ".join(f"{k}={v}" for k, v in list(comps.items())[:6])
            lines.append(f"Factor breakdown: {parts}")
        return "\n".join(lines)

    if any(k in msg_l for k in ("review my project", "analyse my project", "analyze my project")):
        if projects:
            lines.append("Projects on file:")
            lines.extend(f"• {p}" for p in projects[:6])
            lines.append(
                "For deeper code evidence, paste a public GitHub URL in the Projects page and run Analyze."
            )
        else:
            lines.append(
                "No projects saved yet. Add a project or GitHub URL so review can stay factual."
            )
        return "\n".join(lines)

    # Generic but still question-specific
    lines.append(f"Regarding your question — “{msg[:300]}” — here is profile-grounded guidance:")
    if focus:
        lines.append(
            f"Continuing from our recent focus on {focus}: connect your next step to that skill "
            "unless you want to change direction."
        )
    elif actions:
        lines.append("Practical next steps from your dashboard signals:")
        lines.extend(f"• {a}" for a in actions)
    else:
        lines.append(
            "Update skills, preferred roles, and projects so coaching can be more specific."
        )
    lines.append(
        "You can ask follow-ups like what to learn next, why, a 30-day plan, or which project to build."
    )
    return "\n".join(lines)


def ask_coach(
    profile: StudentProfile,
    message: str,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    """Call the configured AI provider with grounded student context + history."""
    message = (message or "").strip()
    if not message:
        return {"provider": "none", "reply": "Please enter a question.", "context_skills": []}

    context = build_student_context(profile)
    history = recent_conversation(profile, limit=HISTORY_WINDOW)

    grounded_message = (
        f"{message}\n\n"
        "[Constraint] Only reference skills from this list: "
        f"{', '.join(context['skill_names']) or '(none on file)'}. "
        "Answer the current question; use conversation history for follow-ups."
    )

    provider_name = "local-demo"
    reply = ""
    try:
        provider = get_ai_provider(current_app.config)
        provider_name = getattr(provider, "name", provider_name)
        if provider_name in {"local", "local-demo", "demo"}:
            reply = _local_smart_reply(message, context, history)
        else:
            reply = provider.complete(
                grounded_message,
                system=_SYSTEM_PROMPT,
                context=context,
                history=history,
            )
    except Exception:  # noqa: BLE001 — never crash coach UX
        provider_name = "local-fallback"
        reply = _local_smart_reply(message, context, history)
        reply += "\n\n(Note: cloud provider unavailable — using local coach.)"

    if persist:
        # Avoid duplicate user rows if the same message was just saved (double submit).
        last_user = (
            AIConversation.query.filter_by(student_id=profile.id, role="user")
            .order_by(AIConversation.created_at.desc())
            .first()
        )
        if last_user is None or (last_user.message or "").strip() != message:
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
                        "history_turns": len(history),
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
