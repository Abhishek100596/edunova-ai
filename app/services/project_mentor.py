"""Project mentor — grounded advice from saved project / GitHub analysis."""

from __future__ import annotations

import json
from typing import Any

from app.models.experience import Project
from app.models.profile import StudentProfile


def _parse_analysis(project: Project) -> dict[str, Any]:
    if hasattr(project, "analysis_dict") and callable(project.analysis_dict):
        data = project.analysis_dict()
        if isinstance(data, dict):
            return data
    raw = getattr(project, "analysis_json", None)
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}


def mentor_project(project: Project, profile: StudentProfile | None = None) -> dict[str, Any]:
    """
    Deterministic mentor report from project fields + optional GitHub analysis.

    Never claims features that are not evidenced in the saved analysis.
    """
    analysis = _parse_analysis(project)
    found = analysis.get("found_in_repository") if isinstance(analysis, dict) else {}
    inferred = analysis.get("inferred_from_code") if isinstance(analysis, dict) else {}
    if not isinstance(found, dict):
        found = {}
    if not isinstance(inferred, dict):
        inferred = {}

    languages = list(found.get("languages") or [])
    frameworks = list(found.get("frameworks") or [])
    features = list(found.get("features") or [])
    gaps = list(inferred.get("possible_skill_gaps") or [])
    bullets = list(inferred.get("resume_bullets") or [])
    clues = list(found.get("architecture_clues") or [])

    tech = []
    if project.tech_stack:
        tech = [t.strip() for t in str(project.tech_stack).split(",") if t.strip()]
    stack = languages or frameworks or tech

    strengths: list[str] = []
    if stack:
        strengths.append(f"Uses a visible stack: {', '.join(stack[:6])}.")
    if features:
        strengths.append(f"Repository signals include: {', '.join(features[:5])}.")
    if clues:
        strengths.append(clues[0])
    if project.description:
        strengths.append("Project description is present on your EduNova profile.")

    weaknesses: list[str] = []
    if not project.description:
        weaknesses.append("Add a short project description for recruiters.")
    if "Testing" not in features and not any("test" in g.lower() for g in gaps):
        weaknesses.append("Automated tests are not clearly evidenced.")
    for g in gaps[:4]:
        weaknesses.append(str(g))

    improvements = [
        "Document setup and run steps in a README if missing.",
        "Add one measurable outcome (users, latency, accuracy) if you have real data.",
        "Prepare a 60-second walkthrough of architecture and trade-offs.",
    ]
    if not frameworks and tech:
        improvements.append("Call out frameworks/libraries explicitly in the tech stack.")

    interview_qs = [
        f"Walk me through how you built {project.title}.",
        "What was the hardest bug or design decision?",
        "How would you improve this project in two weeks?",
    ]
    if stack:
        interview_qs.append(f"Why did you choose {stack[0]} for this project?")

    github_available = bool(found) or (project.analysis_status == "analyzed")
    summary = (
        f"{project.title} — "
        + (
            "GitHub-backed analysis available."
            if github_available
            else "Manual project entry (no GitHub analysis on file)."
        )
    )

    preferred = None
    if profile and profile.preferred_roles:
        preferred = str(profile.preferred_roles)

    return {
        "ok": True,
        "project_id": project.id,
        "title": project.title,
        "summary": summary,
        "technologies": stack[:12],
        "strengths": strengths or ["Project is saved on your profile."],
        "weaknesses": weaknesses or ["No major gaps detected from available evidence."],
        "missing_practices": gaps[:6],
        "improvements": improvements,
        "interview_questions": interview_qs,
        "resume_bullets": bullets
        or [
            f"Built {project.title}"
            + (f" using {', '.join(stack[:3])}" if stack else "")
            + "."
        ],
        "portfolio_advice": (
            f"Present this project toward {preferred}."
            if preferred
            else "Align the project story to your target role on your profile."
        ),
        "next_features": [
            "Add tests for one critical path",
            "Add a short demo GIF or screenshots",
            "Write a README with architecture overview",
        ],
        "github_available": github_available,
        "disclaimer": (
            "Mentor suggestions are educational and based only on saved project data. "
            "Features not evidenced were not assumed."
        ),
    }
