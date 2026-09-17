"""Career coach — profile context + conversation memory + AI provider."""

from __future__ import annotations

import json
import re
from typing import Any

from flask import current_app

from app.ai.provider import complete_with_fallback
from app.ai.response import markdown_to_safe_html, normalize_ai_text
from app.extensions import db
from app.models.analytics import AIConversation
from app.models.experience import Certification, Internship, Project
from app.models.profile import StudentProfile
from app.models.skills import StudentSkill
from app.models.user import User

HISTORY_WINDOW = 16

COACH_SYSTEM_PROMPT = """You are EDUNOVA AI Career Coach — a practical mentor for college students.

Voice:
- Clear, encouraging, and concrete.
- Student-friendly natural language (not a Python console, not JSON).
- Prefer short paragraphs, bullets, and numbered steps.

Hard rules:
1. Use ONLY the provided student profile facts and conversation history.
2. Never invent skills, projects, internships, certifications, grades, companies, or experience.
3. Clearly distinguish: (a) profile facts, (b) calculated EduNova metrics, (c) recommendations.
4. If important data is missing, say exactly what to add in EduNova.
5. Answer the CURRENT question. For follow-ups (why?, how?, what next?, make a plan), continue the prior topic.
6. Do not return JSON, Python dictionaries, or code unless the student explicitly asks for code.
7. Do not repeat previous answers verbatim — add new useful detail.
8. Scores and fit percentages are educational estimates, not hiring guarantees.

When giving career / learning guidance, structure as:
- WHAT TO LEARN
- WHY (tied to their profile/role)
- HOW TO PRACTICE
- PROJECT IDEA (realistic for their skills)
- TIMELINE (e.g. 2–4 weeks or 30 days)
- INTERVIEW PREPARATION
- NEXT ACTION (one immediate step)
"""


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


def _local_smart_reply(
    message: str,
    context: dict[str, Any],
    history: list[dict[str, str]] | None = None,
) -> str:
    """Natural deterministic coaching — no internal demo labels."""
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

    lines: list[str] = []

    def _gap_skill() -> str | None:
        gaps = top.get("gaps") or []
        if gaps:
            g0 = gaps[0]
            return g0.get("skill_name") if isinstance(g0, dict) else str(g0)
        return focus

    if any(k in msg_l for k in ("why should i learn", "why that", "why this", "why learn")):
        topic = focus or _gap_skill() or (skills[0] if skills else "a core skill")
        role_name = top.get("role_name") or (roles[0] if roles else "your target role")
        lines.append(
            f"**Why {topic}?**\n\n"
            f"Based on your saved profile, {topic} closes a documented gap for "
            f"**{role_name}** and strengthens evidence recruiters look for on that track."
        )
        if readiness is not None:
            lines.append(f"Your current readiness estimate is **{readiness}/100** (educational estimate).")
        return "\n\n".join(lines)

    if any(k in msg_l for k in ("30 day", "30-day", "study plan", "learning plan", "make a plan")):
        topic = focus or _gap_skill() or (skills[0] if skills else "fundamentals")
        lines.append(f"**30-day plan focused on {topic}**\n")
        lines.append(f"1. **Days 1–7:** Fundamentals of {topic} (concepts + short exercises).")
        lines.append(f"2. **Days 8–14:** Guided tutorials applying {topic} to a tiny dataset or feature.")
        lines.append(f"3. **Days 15–21:** Build a small demo that uses {topic} and document results.")
        lines.append(
            f"4. **Days 22–30:** Polish README, practice explaining {topic} in interviews, "
            "and mark related roadmap tasks complete in EduNova."
        )
        return "\n".join(lines)

    if any(k in msg_l for k in ("what project", "which project", "project should")):
        topic = focus or _gap_skill() or "your strongest skill"
        lines.append(
            f"Build a portfolio project that showcases **{topic}** end-to-end "
            "(problem → implementation → result → short write-up)."
        )
        if projects:
            lines.append(
                "You already list:\n"
                + "\n".join(f"• {p}" for p in projects[:4])
                + "\n\nExtend one of these or start a focused new demo around that skill."
            )
        else:
            lines.append(
                "You have no projects on file yet — add a GitHub repo in **Projects** so advice stays concrete."
            )
        return "\n\n".join(lines)

    if any(k in msg_l for k in ("missing", "skill gap", "skills am i")):
        gaps = top.get("gaps") or []
        if gaps:
            lines.append(
                f"For **{top.get('role_name') or 'your top catalog role'}**, these skills look below target:"
            )
            for g in gaps[:6]:
                name = g.get("skill_name") if isinstance(g, dict) else str(g)
                lines.append(f"• {name}")
        else:
            lines.append(
                "No large gaps were computed yet. Set a preferred role and skills, then regenerate analysis."
            )
        return "\n".join(lines)

    if any(
        k in msg_l
        for k in ("learn next", "what should i learn", "improve my skills", "how do i improve")
    ):
        topic = _gap_skill()
        if topic:
            lines.append(f"**Next learning focus: {topic}**")
            lines.append(
                f"It is the highest-priority gap for "
                f"**{top.get('role_name') or (roles[0] if roles else 'your target role')}** "
                f"on your current profile."
            )
            if skills:
                lines.append("Skills already on file: " + ", ".join(skills[:10]))
            lines.append(
                'Ask “Why should I learn that?” or “Give me a 30 day plan” for a follow-up.'
            )
        elif actions:
            lines.append("Suggested next actions from your data:")
            lines.extend(f"• {a}" for a in actions)
        else:
            lines.append(
                "Add a target role and skills so EduNova can prioritize what to learn next."
            )
        return "\n\n".join(lines)

    if any(k in msg_l for k in ("roadmap", "career path", "become a", "suitable for me")):
        if top:
            lines.append(
                f"A suitable near-term catalog direction is **{top.get('role_name')}** "
                f"at about **{top.get('match_pct')}%** current match (estimate)."
            )
        if roles:
            lines.append("Preferred roles on profile: " + ", ".join(str(r) for r in roles[:5]))
        lines.append(
            "Open **Learning Roadmap** and generate a plan for that role so progress persists."
        )
        return "\n\n".join(lines)

    if any(k in msg_l for k in ("company", "companies should", "target next")):
        targets = context.get("target_companies") or []
        lines.append(
            "Company targeting uses your saved target list and educational compatibility estimates."
        )
        if targets:
            lines.append("Targets on profile: " + ", ".join(str(t) for t in targets[:8]))
        lines.append("Use **Company Comparison** to see fit percentages and missing skills side by side.")
        return "\n\n".join(lines)

    if "resume" in msg_l:
        lines.append(
            "Resume tip: quantify outcomes on projects already listed; never invent experience."
        )
        if projects:
            lines.append("Project evidence available:\n" + "\n".join(f"• {p}" for p in projects[:3]))
        return "\n\n".join(lines)

    if "interview" in msg_l:
        kind = (
            "technical"
            if "technical" in msg_l
            else ("HR" if "hr" in msg_l else "behavioral/technical")
        )
        lines.append(
            f"For **{kind}** interview prep: practice role-specific questions using only skills "
            "and projects on your profile."
        )
        lines.append("Use **Interview Prep** in EduNova to run a scored mock session.")
        return "\n\n".join(lines)

    if any(k in msg_l for k in ("ready", "readiness", "placement readiness")):
        lines.append(
            "Readiness is a weighted estimate from academics, skills, projects, experience, "
            "certifications, and interview history — not a placement promise."
        )
        if readiness is not None:
            lines.append(f"Current readiness estimate: **{readiness}/100**.")
        comps = context.get("readiness_components") or {}
        if comps:
            parts = ", ".join(f"{k}={v}" for k, v in list(comps.items())[:6])
            lines.append(f"Factor breakdown: {parts}")
        return "\n\n".join(lines)

    if any(k in msg_l for k in ("review my project", "analyse my project", "analyze my project")):
        if projects:
            lines.append("Projects on file:")
            lines.extend(f"• {p}" for p in projects[:6])
            lines.append(
                "For deeper code evidence, paste a public GitHub URL in **Projects** and run Analyze."
            )
        else:
            lines.append(
                "No projects saved yet. Add a project or GitHub URL so review can stay factual."
            )
        return "\n\n".join(lines)

    # Generic but question-aware
    greeting = context.get("name") or "there"
    lines.append(f"Hi {greeting.split()[0] if greeting else 'there'} — here's guidance on your question.")
    if focus:
        lines.append(
            f"Continuing from our recent focus on **{focus}**: connect your next step to that skill "
            "unless you want to change direction."
        )
    elif actions:
        lines.append("Practical next steps from your dashboard signals:")
        lines.extend(f"• {a}" for a in actions)
    else:
        lines.append(
            "Update skills, preferred roles, and projects so coaching can be more specific."
        )
    if skills:
        lines.append("Skills on file: " + ", ".join(skills[:10]))
    lines.append(
        "You can ask follow-ups like what to learn next, why, a 30-day plan, or which project to build."
    )
    return "\n\n".join(lines)


def ask_coach(
    profile: StudentProfile,
    message: str,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    """Call configured AI with grounded context + history; normalize for UI."""
    message = (message or "").strip()
    if not message:
        return {
            "provider": "none",
            "reply": "Please enter a question.",
            "reply_html": markdown_to_safe_html("Please enter a question."),
            "context_skills": [],
            "fallback_used": False,
            "status_message": "",
        }

    context = build_student_context(profile)
    history = recent_conversation(profile, limit=HISTORY_WINDOW)

    grounded_message = (
        f"{message}\n\n"
        "[Constraint] Only reference skills from this list: "
        f"{', '.join(context['skill_names']) or '(none on file)'}. "
        "Answer the current question; use conversation history for follow-ups. "
        "Respond in natural language, not JSON."
    )

    primary = str(current_app.config.get("AI_PROVIDER", "local") or "local").lower()
    if primary in {"local", "demo", "local-demo"}:
        reply = normalize_ai_text(_local_smart_reply(message, context, history))
        provider_name = "local"
        fallback_used = False
        status_message = ""
    else:
        result = complete_with_fallback(
            current_app.config,
            grounded_message,
            system=COACH_SYSTEM_PROMPT,
            context=context,
            history=history,
        )
        reply = normalize_ai_text(result["reply"])
        provider_name = result["provider"]
        fallback_used = bool(result.get("fallback_used"))
        status_message = result.get("status_message") or ""
        # If cloud failed into local, enrich with smarter local reply
        if provider_name in {"local", "local-demo"} and fallback_used:
            reply = normalize_ai_text(_local_smart_reply(message, context, history))

    if persist:
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
                        "fallback_used": fallback_used,
                    }
                ),
            )
        )
        db.session.commit()

    return {
        "provider": provider_name,
        "reply": reply,
        "reply_html": markdown_to_safe_html(reply),
        "context_skills": context["skill_names"],
        "fallback_used": fallback_used,
        "status_message": status_message,
    }


def clear_conversation(profile: StudentProfile) -> int:
    rows = AIConversation.query.filter_by(student_id=profile.id).all()
    count = len(rows)
    for row in rows:
        db.session.delete(row)
    db.session.commit()
    return count


def provider_display_name(app_config=None) -> str:
    cfg = app_config or current_app.config
    name = str(cfg.get("AI_PROVIDER", "local") or "local").strip().lower()
    labels = {
        "groq": "Groq",
        "openai": "OpenAI",
        "gpt": "OpenAI",
        "gemini": "Gemini",
        "google": "Gemini",
        "local": "EduNova local",
        "demo": "EduNova local",
        "local-demo": "EduNova local",
    }
    return labels.get(name, name.title())
