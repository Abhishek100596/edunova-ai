"""Deterministic placement-readiness component scores (0–100)."""

from __future__ import annotations

from typing import Any

from app.models.experience import Certification, Internship, Project
from app.models.interview import InterviewSession
from app.models.profile import StudentProfile
from app.models.skills import StudentSkill


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def academic_readiness(profile: StudentProfile) -> float:
    cgpa = float(profile.cgpa) if profile.cgpa is not None else 0.0
    # Assume 10-point scale; if value looks like 4-point, scale up.
    if 0 < cgpa <= 4.0:
        cgpa_10 = cgpa * 2.5
    else:
        cgpa_10 = cgpa
    cgpa_score = _clamp((cgpa_10 / 10.0) * 100.0)

    attendance = float(profile.attendance) if profile.attendance is not None else 0.0
    if attendance <= 1.0:
        attendance *= 100.0
    attendance_score = _clamp(attendance)

    backlogs = int(profile.backlogs or 0)
    backlog_penalty = min(40.0, backlogs * 10.0)

    consistency = profile.academic_consistency
    if consistency is None:
        consistency_score = 50.0
    else:
        c = float(consistency)
        consistency_score = _clamp(c * 100.0 if c <= 1.0 else c)

    score = (
        0.45 * cgpa_score
        + 0.25 * attendance_score
        + 0.20 * consistency_score
        + 0.10 * (100.0 - backlog_penalty)
    )
    return round(_clamp(score), 2)


def skill_readiness(profile: StudentProfile) -> float:
    links = StudentSkill.query.filter_by(student_id=profile.id).all()
    if not links:
        return 0.0
    avg_level = sum(max(1, min(5, int(s.level or 1))) for s in links) / len(links)
    count_factor = min(1.0, len(links) / 12.0)
    score = (avg_level / 5.0) * 70.0 + count_factor * 30.0
    return round(_clamp(score), 2)


def project_readiness(profile: StudentProfile) -> float:
    count = Project.query.filter_by(student_id=profile.id).count()
    # 0→0, 1→40, 2→65, 3→80, 4+→95
    thresholds = [(0, 0.0), (1, 40.0), (2, 65.0), (3, 80.0), (4, 95.0)]
    score = 100.0
    for n, s in thresholds:
        if count <= n:
            score = s
            break
    if count > 4:
        score = 100.0
    return round(_clamp(score), 2)


def experience_readiness(profile: StudentProfile) -> float:
    count = Internship.query.filter_by(student_id=profile.id).count()
    if count <= 0:
        return 0.0
    if count == 1:
        return 55.0
    if count == 2:
        return 80.0
    return 100.0


def certification_readiness(profile: StudentProfile) -> float:
    count = Certification.query.filter_by(student_id=profile.id).count()
    if count <= 0:
        return 0.0
    if count == 1:
        return 50.0
    if count == 2:
        return 75.0
    return 100.0


def interview_readiness(profile: StudentProfile) -> float:
    sessions = (
        InterviewSession.query.filter_by(student_id=profile.id, status="completed")
        .all()
    )
    if not sessions:
        return 0.0
    scores: list[float] = []
    for session in sessions:
        if session.overall_score is not None:
            scores.append(float(session.overall_score))
            continue
        q_scores: list[float] = []
        for q in session.questions or []:
            ans = q.answer
            if ans is not None and ans.score is not None:
                q_scores.append(float(ans.score))
        if q_scores:
            scores.append(sum(q_scores) / len(q_scores))
    if not scores:
        # Attempted interviews without scores still show modest progress.
        return round(_clamp(min(40.0, 15.0 * len(sessions))), 2)
    avg = sum(scores) / len(scores)
    # Normalize if scores stored 0–1.
    if avg <= 1.0:
        avg *= 100.0
    return round(_clamp(avg), 2)


def compute_all_readiness(profile: StudentProfile) -> dict[str, float]:
    return {
        "academic": academic_readiness(profile),
        "skill": skill_readiness(profile),
        "project": project_readiness(profile),
        "experience": experience_readiness(profile),
        "certification": certification_readiness(profile),
        "interview": interview_readiness(profile),
    }


def overall_readiness(profile: StudentProfile, weights: dict[str, float] | None = None) -> float:
    parts = compute_all_readiness(profile)
    w = weights or {
        "academic": 0.25,
        "skill": 0.25,
        "project": 0.15,
        "experience": 0.15,
        "certification": 0.10,
        "interview": 0.10,
    }
    total_w = sum(w.values()) or 1.0
    score = sum(parts[k] * w.get(k, 0.0) for k in parts) / total_w
    return round(_clamp(score), 2)


def readiness_breakdown(profile: StudentProfile) -> dict[str, Any]:
    parts = compute_all_readiness(profile)
    return {
        "components": parts,
        "overall": overall_readiness(profile),
    }
