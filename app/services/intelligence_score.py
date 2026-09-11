"""EDUNOVA Intelligence Score — deterministic weighted dimensions."""

from __future__ import annotations

from typing import Any

from app.models.learning import LearningRoadmap, LearningTask
from app.models.profile import StudentProfile
from app.models.resume import Resume, ResumeAnalysis
from app.services.career import match_roles
from app.services.skill_confidence import compute_skill_confidence
from app.utils.readiness import (
    academic_readiness,
    certification_readiness,
    experience_readiness,
    interview_readiness,
    project_readiness,
    skill_readiness,
)

# Fixed weights — sum to 1.0; never random.
DIMENSION_WEIGHTS: dict[str, float] = {
    "academic": 0.12,
    "technical": 0.14,
    "projects": 0.12,
    "experience": 0.10,
    "resume": 0.10,
    "career_alignment": 0.12,
    "interview": 0.10,
    "certifications": 0.08,
    "learning_progress": 0.06,
    "evidence_strength": 0.06,
}


def _latest_resume_score(profile: StudentProfile) -> tuple[float, str]:
    resumes = (
        Resume.query.filter_by(student_id=profile.id)
        .order_by(Resume.uploaded_at.desc())
        .all()
    )
    for resume in resumes:
        analysis = (
            ResumeAnalysis.query.filter_by(resume_id=resume.id)
            .order_by(ResumeAnalysis.created_at.desc())
            .first()
        )
        if analysis is not None:
            return (
                float(analysis.completeness_score or 0.0),
                "Latest ResumeAnalysis.completeness_score",
            )
    return 0.0, "No ResumeAnalysis found — resume dimension set to 0"


def _learning_progress(profile: StudentProfile) -> float:
    roadmaps = LearningRoadmap.query.filter_by(student_id=profile.id).all()
    if not roadmaps:
        return 0.0
    pcts: list[float] = []
    for rm in roadmaps:
        if rm.progress_pct is not None and float(rm.progress_pct) > 0:
            pcts.append(float(rm.progress_pct))
            continue
        tasks = LearningTask.query.filter_by(roadmap_id=rm.id).all()
        if not tasks:
            pcts.append(0.0)
            continue
        done = sum(1 for t in tasks if (t.status or "") == "completed")
        pcts.append((done / len(tasks)) * 100.0)
    return round(sum(pcts) / len(pcts), 2) if pcts else 0.0


def _evidence_strength(profile: StudentProfile) -> float:
    rows = compute_skill_confidence(profile)
    if not rows:
        return 0.0
    avg = sum(float(r["confidence"]) for r in rows) / len(rows)
    return round(avg * 100.0, 2)


def compute_intelligence_score(profile: StudentProfile) -> dict[str, Any]:
    """
    EDUNOVA Intelligence Score with how_calculated strings.
    All values deterministic from profile + related tables.
    """
    academic = academic_readiness(profile)
    technical = skill_readiness(profile)
    projects = project_readiness(profile)
    experience = experience_readiness(profile)
    resume_score, resume_note = _latest_resume_score(profile)
    roles = match_roles(profile, limit=1)
    career_alignment = float(roles[0]["match_pct"]) if roles else 0.0
    interview = interview_readiness(profile)
    certifications = certification_readiness(profile)
    learning_progress = _learning_progress(profile)
    evidence_strength = _evidence_strength(profile)

    dimensions: dict[str, dict[str, Any]] = {
        "academic": {
            "score": academic,
            "weight": DIMENSION_WEIGHTS["academic"],
            "how_calculated": (
                "Weighted mix of CGPA (scaled), attendance, academic consistency, "
                "and backlog penalty from readiness.academic_readiness"
            ),
        },
        "technical": {
            "score": technical,
            "weight": DIMENSION_WEIGHTS["technical"],
            "how_calculated": (
                "Average StudentSkill level (1–5) plus skill-count breadth factor "
                "from readiness.skill_readiness"
            ),
        },
        "projects": {
            "score": projects,
            "weight": DIMENSION_WEIGHTS["projects"],
            "how_calculated": (
                "Step function on Project count (0→0 … 4+→95/100) "
                "from readiness.project_readiness"
            ),
        },
        "experience": {
            "score": experience,
            "weight": DIMENSION_WEIGHTS["experience"],
            "how_calculated": (
                "Internship count thresholds from readiness.experience_readiness"
            ),
        },
        "resume": {
            "score": round(resume_score, 2),
            "weight": DIMENSION_WEIGHTS["resume"],
            "how_calculated": resume_note,
        },
        "career_alignment": {
            "score": career_alignment,
            "weight": DIMENSION_WEIGHTS["career_alignment"],
            "how_calculated": (
                "Top match_roles() match_pct against CareerRole / RoleSkill catalog"
            ),
        },
        "interview": {
            "score": interview,
            "weight": DIMENSION_WEIGHTS["interview"],
            "how_calculated": (
                "Average completed InterviewSession scores from "
                "readiness.interview_readiness"
            ),
        },
        "certifications": {
            "score": certifications,
            "weight": DIMENSION_WEIGHTS["certifications"],
            "how_calculated": (
                "Certification count thresholds from readiness.certification_readiness"
            ),
        },
        "learning_progress": {
            "score": learning_progress,
            "weight": DIMENSION_WEIGHTS["learning_progress"],
            "how_calculated": (
                "Average LearningRoadmap progress_pct or completed-task ratio"
            ),
        },
        "evidence_strength": {
            "score": evidence_strength,
            "weight": DIMENSION_WEIGHTS["evidence_strength"],
            "how_calculated": (
                "Mean skill confidence (level + project/cert/internship/interview "
                "evidence bits) scaled to 0–100"
            ),
        },
    }

    overall = 0.0
    for dim in dimensions.values():
        overall += float(dim["score"]) * float(dim["weight"])
    overall = round(overall, 2)

    return {
        "brand": "EDUNOVA AI",
        "score_name": "EDUNOVA Intelligence Score",
        "overall": overall,
        "dimensions": dimensions,
        "weights": dict(DIMENSION_WEIGHTS),
        "how_calculated_overall": (
            "Weighted sum of dimension scores using fixed DIMENSION_WEIGHTS "
            "(academic 12%, technical 14%, projects 12%, experience 10%, resume 10%, "
            "career_alignment 12%, interview 10%, certifications 8%, "
            "learning_progress 6%, evidence_strength 6%). Never random."
        ),
        "disclaimer": (
            "Educational readiness estimate only — not a hiring decision or "
            "guarantee of placement outcomes."
        ),
    }
