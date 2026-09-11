"""Deterministic skill confidence from profile evidence bits (no randomness)."""

from __future__ import annotations

import re
from typing import Any

from app.models.experience import Certification, Internship, Project
from app.models.interview import InterviewSession
from app.models.profile import StudentProfile
from app.models.skills import Skill, StudentSkill


def _clamp01(x: float) -> float:
    return float(max(0.0, min(1.0, x)))


def _confidence_label(confidence: float) -> str:
    if confidence >= 0.75:
        return "High"
    if confidence >= 0.45:
        return "Medium"
    if confidence >= 0.20:
        return "Low"
    return "Not evidenced"


def _skill_mentioned(text: str, skill_name: str) -> bool:
    if not text or not skill_name:
        return False
    pattern = re.compile(
        r"(?<![a-z0-9])" + re.escape(skill_name.lower()) + r"(?![a-z0-9])",
        re.I,
    )
    return bool(pattern.search(text.lower()))


def compute_skill_confidence(profile: StudentProfile) -> list[dict[str, Any]]:
    """
    For each StudentSkill, score confidence 0–1 from:
    level, project mentions, certification title keywords, internship text,
    and interview scores when present.
    """
    links = (
        StudentSkill.query.filter_by(student_id=profile.id)
        .join(Skill)
        .order_by(Skill.name.asc())
        .all()
    )
    projects = Project.query.filter_by(student_id=profile.id).all()
    certs = Certification.query.filter_by(student_id=profile.id).all()
    internships = Internship.query.filter_by(student_id=profile.id).all()
    sessions = (
        InterviewSession.query.filter_by(student_id=profile.id, status="completed")
        .all()
    )

    interview_avg: float | None = None
    scores: list[float] = []
    for session in sessions:
        if session.overall_score is not None:
            val = float(session.overall_score)
            scores.append(val * 100.0 if val <= 1.0 else val)
            continue
        q_scores: list[float] = []
        for q in session.questions or []:
            ans = q.answer
            if ans is not None and ans.score is not None:
                v = float(ans.score)
                q_scores.append(v * 100.0 if v <= 1.0 else v)
        if q_scores:
            scores.append(sum(q_scores) / len(q_scores))
    if scores:
        interview_avg = sum(scores) / len(scores)

    results: list[dict[str, Any]] = []
    for link in links:
        skill = link.skill
        name = skill.name if skill else f"skill#{link.skill_id}"
        level = max(1, min(5, int(link.level or 1)))
        evidence_bits: list[str] = [f"Declared level {level}/5"]

        # Level contributes up to 0.45
        conf = (level / 5.0) * 0.45

        project_hits = 0
        for p in projects:
            blob = " ".join(
                filter(
                    None,
                    [p.title or "", p.description or "", p.tech_stack or ""],
                )
            )
            if _skill_mentioned(blob, name):
                project_hits += 1
        if project_hits:
            bump = min(0.25, 0.10 + 0.05 * project_hits)
            conf += bump
            evidence_bits.append(f"Mentioned in {project_hits} project(s)")

        cert_hits = 0
        for c in certs:
            blob = " ".join(filter(None, [c.name or "", c.issuer or ""]))
            if _skill_mentioned(blob, name):
                cert_hits += 1
        if cert_hits:
            bump = min(0.15, 0.08 * cert_hits)
            conf += bump
            evidence_bits.append(f"Certification keyword match ({cert_hits})")

        intern_hits = 0
        for intern in internships:
            blob = " ".join(
                filter(
                    None,
                    [
                        intern.title or "",
                        intern.description or "",
                        intern.company or "",
                    ],
                )
            )
            if _skill_mentioned(blob, name):
                intern_hits += 1
        if intern_hits:
            bump = min(0.10, 0.06 * intern_hits)
            conf += bump
            evidence_bits.append(f"Internship text match ({intern_hits})")

        if interview_avg is not None:
            # Shared interview signal — modest boost for all skills when interviews exist
            interview_bump = min(0.10, (interview_avg / 100.0) * 0.10)
            conf += interview_bump
            evidence_bits.append(
                f"Completed interview avg score {interview_avg:.1f}"
            )

        conf = _clamp01(conf)
        if conf < 0.20 and len(evidence_bits) <= 1:
            evidence_bits.append("No external portfolio / cert / internship evidence")

        results.append(
            {
                "skill": name,
                "skill_id": link.skill_id,
                "level": level,
                "confidence": round(conf, 4),
                "label": _confidence_label(conf),
                "evidence_bits": evidence_bits,
            }
        )

    results.sort(key=lambda r: (-r["confidence"], r["skill"]))
    return results
