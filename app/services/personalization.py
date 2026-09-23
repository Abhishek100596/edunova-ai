"""Central personalization / recommendation context for EDUNOVA features."""

from __future__ import annotations

from typing import Any

from app.models.analytics import PredictionRecord, ProgressRecord
from app.models.experience import Certification, Internship, Project
from app.models.interview import InterviewSession
from app.models.learning import LearningRoadmap
from app.models.profile import StudentProfile
from app.models.research import Company, UserTarget
from app.models.resume import Resume, ResumeAnalysis
from app.models.skills import StudentSkill
from app.services.career import match_roles
from app.services.intelligence_score import compute_intelligence_score
from app.services.skill_confidence import compute_skill_confidence
from app.utils.readiness import readiness_breakdown


def get_user_profile_context(profile: StudentProfile) -> dict[str, Any]:
    skills = []
    for row in StudentSkill.query.filter_by(student_id=profile.id).all():
        skills.append(
            {
                "id": row.skill_id,
                "name": row.skill.name if row.skill else f"skill#{row.skill_id}",
                "level": row.level,
                "category": row.skill.category if row.skill else None,
            }
        )
    return {
        "profile_id": profile.id,
        "college": profile.college,
        "degree": profile.degree,
        "branch": profile.branch,
        "cgpa": profile.cgpa,
        "skills": skills,
        "preferred_roles": profile.preferred_roles,
        "target_companies": profile.target_companies,
        "project_count": Project.query.filter_by(student_id=profile.id).count(),
        "internship_count": Internship.query.filter_by(student_id=profile.id).count(),
        "certification_count": Certification.query.filter_by(student_id=profile.id).count(),
    }


def calculate_readiness(profile: StudentProfile) -> dict[str, Any]:
    return readiness_breakdown(profile)


def get_career_matches(profile: StudentProfile, limit: int = 5) -> list[dict[str, Any]]:
    return match_roles(profile, limit=limit)


def get_roadmap_progress(profile: StudentProfile) -> dict[str, Any]:
    roadmaps = (
        LearningRoadmap.query.filter_by(student_id=profile.id)
        .order_by(LearningRoadmap.updated_at.desc())
        .all()
    )
    if not roadmaps:
        return {"has_roadmap": False, "progress_pct": 0.0, "title": None}
    top = roadmaps[0]
    return {
        "has_roadmap": True,
        "progress_pct": float(top.progress_pct or 0.0),
        "title": top.title,
        "role_id": top.role_id,
        "roadmap_id": top.id,
    }


def get_resume_summary(profile: StudentProfile) -> dict[str, Any]:
    resume = (
        Resume.query.filter_by(student_id=profile.id)
        .order_by(Resume.uploaded_at.desc())
        .first()
    )
    if resume is None:
        return {"has_resume": False}
    analysis = (
        ResumeAnalysis.query.filter_by(resume_id=resume.id)
        .order_by(ResumeAnalysis.created_at.desc())
        .first()
    )
    return {
        "has_resume": True,
        "resume_id": resume.id,
        "completeness": float(analysis.completeness_score) if analysis else None,
        "original_filename": resume.original_filename,
    }


def get_interview_summary(profile: StudentProfile) -> dict[str, Any]:
    sessions = (
        InterviewSession.query.filter_by(student_id=profile.id)
        .order_by(InterviewSession.started_at.desc())
        .all()
    )
    completed = [s for s in sessions if s.status == "completed"]
    avg = None
    if completed:
        scores = [float(s.overall_score) for s in completed if s.overall_score is not None]
        if scores:
            avg = round(sum(scores) / len(scores), 3)
    return {
        "session_count": len(sessions),
        "completed_count": len(completed),
        "average_score": avg,
        "latest_summary": completed[0].summary if completed else None,
    }


def get_company_matches(profile: StudentProfile, limit: int = 5) -> list[dict[str, Any]]:
    try:
        from app.services.company_intel import opportunity_fit

        data = opportunity_fit(profile)
        return list(data.get("opportunities") or [])[:limit]
    except Exception:
        return []


def get_readiness_history(profile: StudentProfile) -> dict[str, Any]:
    rows = (
        ProgressRecord.query.filter_by(
            student_id=profile.id, metric_name="readiness_demo_history"
        )
        .order_by(ProgressRecord.recorded_at.asc())
        .all()
    )
    if not rows:
        rows = (
            ProgressRecord.query.filter(
                ProgressRecord.student_id == profile.id,
                ProgressRecord.metric_name.ilike("%readiness%"),
            )
            .order_by(ProgressRecord.recorded_at.asc())
            .all()
        )
    if not rows:
        return {
            "points": [],
            "is_demo_sample": False,
            "message": "Not enough historical data yet.",
        }
    is_demo = any(r.metric_name == "readiness_demo_history" for r in rows)
    return {
        "points": [
            {
                "label": r.recorded_at.strftime("%Y-%m-%d") if r.recorded_at else str(i + 1),
                "value": float(r.metric_value),
            }
            for i, r in enumerate(rows)
        ],
        "is_demo_sample": is_demo,
        "message": "Demo/sample history" if is_demo else "Recorded readiness history",
    }


def recommend_next_actions(profile: StudentProfile) -> list[dict[str, Any]]:
    """Transparent deterministic recommendations from gaps and progress."""
    actions: list[dict[str, Any]] = []
    matches = get_career_matches(profile, limit=1)
    roadmap = get_roadmap_progress(profile)
    resume = get_resume_summary(profile)
    interview = get_interview_summary(profile)
    readiness = calculate_readiness(profile)

    if matches:
        top = matches[0]
        missing = top.get("missing_skills") or top.get("gaps") or []
        if isinstance(missing, list) and missing:
            first = missing[0]
            name = first.get("skill_name") if isinstance(first, dict) else str(first)
            actions.append(
                {
                    "title": f"Close skill gap: {name}",
                    "reason": f"Top match {top.get('role_name')} still needs this skill.",
                    "href": "student.skill_gap",
                }
            )
        actions.append(
            {
                "title": f"Review {top.get('role_name')} fit ({top.get('match_pct')}%)",
                "reason": "Your strongest current catalog career match.",
                "href": "student.careers",
            }
        )

    if not roadmap.get("has_roadmap"):
        actions.append(
            {
                "title": "Generate a learning roadmap",
                "reason": "No roadmap yet for your target role.",
                "href": "student.roadmap",
            }
        )
    elif float(roadmap.get("progress_pct") or 0) < 80:
        actions.append(
            {
                "title": "Continue roadmap stage",
                "reason": f"Roadmap at {roadmap.get('progress_pct')}% — keep momentum.",
                "href": "student.roadmap",
            }
        )

    if not resume.get("has_resume"):
        actions.append(
            {
                "title": "Analyze your resume",
                "reason": "No resume analysis on file yet.",
                "href": "student.resume",
            }
        )

    if interview.get("completed_count", 0) == 0:
        actions.append(
            {
                "title": "Start a mock interview",
                "reason": "Interview practice improves readiness explainability.",
                "href": "student.interview",
            }
        )

    if float(readiness.get("overall") or 0) < 75:
        actions.append(
            {
                "title": "Open My Readiness",
                "reason": f"Overall readiness is {readiness.get('overall')} — review factor gaps.",
                "href": "intelligence.readiness_center",
            }
        )

    # Deduplicate by title, max 5
    seen = set()
    unique = []
    for a in actions:
        if a["title"] in seen:
            continue
        seen.add(a["title"])
        unique.append(a)
        if len(unique) >= 5:
            break
    return unique


def build_career_snapshot(profile: StudentProfile) -> dict[str, Any]:
    """
    Deterministic AI Career Snapshot for the dashboard.

    Grounded only in stored profile / catalog scores — never invents facts.
    """
    readiness = calculate_readiness(profile)
    matches = get_career_matches(profile, limit=3)
    roadmap = get_roadmap_progress(profile)
    interview = get_interview_summary(profile)
    resume = get_resume_summary(profile)
    components = readiness.get("components") or {}

    strengths: list[str] = []
    for key, label in (
        ("skill", "Skill readiness"),
        ("academic", "Academic readiness"),
        ("project", "Project readiness"),
        ("experience", "Experience readiness"),
        ("certification", "Certification readiness"),
        ("interview", "Interview readiness"),
    ):
        val = float(components.get(key) or 0)
        if val >= 70:
            strengths.append(f"{label} is comparatively strong ({val:.0f}/100).")

    gaps: list[str] = []
    if matches:
        top = matches[0]
        missing = top.get("gaps") or top.get("missing_skills") or []
        for item in list(missing)[:4]:
            name = item.get("skill_name") if isinstance(item, dict) else str(item)
            gaps.append(f"Gap toward {top.get('role_name')}: {name}")
    weak_components = sorted(
        ((k, float(v or 0)) for k, v in components.items()),
        key=lambda x: x[1],
    )
    for key, val in weak_components[:2]:
        if val < 60:
            gaps.append(f"{key.replace('_', ' ').title()} readiness is {val:.0f}/100.")

    top_role = matches[0]["role_name"] if matches else None
    priority = (
        f"Focus on closing gaps for {top_role}."
        if top_role and gaps
        else "Complete onboarding and add skills to unlock sharper recommendations."
    )
    project_idea = (
        f"Build a small portfolio project that demonstrates skills needed for {top_role}."
        if top_role
        else "Add a project that showcases your strongest skill."
    )
    interview_focus = (
        f"Practice mock interviews for {top_role}."
        if top_role
        else "Start a short technical mock interview."
    )
    if interview.get("average_score") is not None:
        interview_focus += f" Latest average score: {interview['average_score']}."

    learning = (
        f"Continue roadmap “{roadmap.get('title')}” ({roadmap.get('progress_pct')}%)."
        if roadmap.get("has_roadmap")
        else "Generate a learning roadmap from your skill gaps."
    )
    if not resume.get("has_resume"):
        learning += " Upload a resume for ATS-style feedback."

    return {
        "strongest_areas": strengths[:4]
        or ["Keep building profile evidence — strengths will appear as scores rise."],
        "biggest_gaps": gaps[:5] or ["No major catalog gaps detected yet."],
        "next_priority": priority,
        "project_to_build": project_idea,
        "interview_focus": interview_focus,
        "recommended_learning": learning,
        "source": "deterministic",
        "disclaimer": (
            "Snapshot is derived from your saved EduNova data — educational estimate only."
        ),
    }


def dashboard_intelligence(profile: StudentProfile) -> dict[str, Any]:
    readiness = calculate_readiness(profile)
    matches = get_career_matches(profile, limit=3)
    opportunities = get_company_matches(profile, limit=5)
    intel = compute_intelligence_score(profile)
    return {
        "readiness": readiness,
        "intelligence": intel,
        "career_matches": matches,
        "opportunities": opportunities,
        "roadmap": get_roadmap_progress(profile),
        "resume": get_resume_summary(profile),
        "interview": get_interview_summary(profile),
        "skill_confidence": compute_skill_confidence(profile)[:8],
        "actions": recommend_next_actions(profile),
        "history": get_readiness_history(profile),
        "career_snapshot": build_career_snapshot(profile),
        "tracked_companies": [
            {
                "id": t.id,
                "company": (t.company.name if t.company else t.company_name),
                "status": t.status,
                "target_role": t.target_role,
            }
            for t in UserTarget.query.filter_by(user_id=profile.user_id).all()
        ],
        "disclaimer": (
            "Scores are compatibility / readiness estimates — not hiring guarantees."
        ),
    }
