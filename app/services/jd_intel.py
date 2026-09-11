"""Job-description heuristics and profile-vs-JD comparison."""

from __future__ import annotations

import re
from typing import Any

from app.models.profile import StudentProfile
from app.models.skills import Skill, StudentSkill
from app.services.resume_intel import extract_skills_from_text, tfidf_cosine_match

SENIORITY_PATTERNS = [
    (re.compile(r"\b(intern|internship|trainee)\b", re.I), "intern"),
    (re.compile(r"\b(junior|jr\.?|entry[- ]level|fresher|graduate)\b", re.I), "junior"),
    (re.compile(r"\b(senior|sr\.?)\b", re.I), "senior"),
    (re.compile(r"\b(lead|staff|principal)\b", re.I), "lead"),
    (re.compile(r"\b(mid[- ]level|intermediate)\b", re.I), "mid"),
]

LOCATION_PATTERN = re.compile(
    r"(?i)(?:location|based in|office(?:s)? in|work from)\s*[:\-]?\s*"
    r"([A-Za-z][A-Za-z\s,./\-]{2,60})"
)
TITLE_PATTERN = re.compile(
    r"(?i)(?:job title|position|role)\s*[:\-]\s*([^\n]{3,80})"
)
REQUIRED_SECTION = re.compile(
    r"(?i)(required|requirements|must have|minimum qualifications)"
    r"[:\s]*([\s\S]{0,1200}?)(?=(preferred|nice to have|responsibilities|$))"
)
PREFERRED_SECTION = re.compile(
    r"(?i)(preferred|nice to have|good to have|desired)"
    r"[:\s]*([\s\S]{0,800}?)(?=(responsibilities|about |$))"
)


def extract_jd_structured(text: str) -> dict[str, Any]:
    """Heuristic keyword/section extraction — no invented employer facts."""
    raw = text or ""
    role = None
    m = TITLE_PATTERN.search(raw)
    if m:
        role = m.group(1).strip()
    else:
        # First non-empty line as weak title hint
        for line in raw.splitlines():
            line = line.strip()
            if 3 <= len(line) <= 80 and not line.lower().startswith("http"):
                role = line
                break

    seniority = None
    for pattern, label in SENIORITY_PATTERNS:
        if pattern.search(raw):
            seniority = label
            break

    location = None
    loc_m = LOCATION_PATTERN.search(raw)
    if loc_m:
        location = loc_m.group(1).strip().rstrip(".,;")

    required_blob = raw
    preferred_blob = ""
    req_m = REQUIRED_SECTION.search(raw)
    if req_m:
        required_blob = req_m.group(2)
    pref_m = PREFERRED_SECTION.search(raw)
    if pref_m:
        preferred_blob = pref_m.group(2)

    catalog = Skill.query.order_by(Skill.name.asc()).all()
    required_skills: list[str] = []
    preferred_skills: list[str] = []
    for skill in catalog:
        name = (skill.name or "").strip()
        if not name:
            continue
        pat = re.compile(
            r"(?<![a-z0-9])" + re.escape(name.lower()) + r"(?![a-z0-9])",
            re.I,
        )
        in_req = bool(pat.search(required_blob))
        in_pref = bool(pat.search(preferred_blob)) if preferred_blob else False
        in_all = bool(pat.search(raw))
        if in_req or (in_all and not preferred_blob):
            if name not in required_skills:
                required_skills.append(name)
        elif in_pref:
            if name not in preferred_skills:
                preferred_skills.append(name)

    # Prefer section-specific preferred list; avoid double-counting
    preferred_skills = [s for s in preferred_skills if s not in required_skills]

    return {
        "role": role,
        "seniority": seniority,
        "location": location,
        "skills_required": required_skills,
        "skills_preferred": preferred_skills,
        "extraction_method": "heuristic_keyword_section",
        "notes": (
            "Heuristic extraction only — verify against the original JD. "
            "No URLs or employers were invented."
        ),
    }


def compare_profile_to_jd(profile: StudentProfile, text: str) -> dict[str, Any]:
    """Combine TF-IDF (resume-like profile text) with skill overlap vs JD."""
    structured = extract_jd_structured(text)
    student_skills = {
        (s.skill.name if s.skill else "").strip()
        for s in StudentSkill.query.filter_by(student_id=profile.id).all()
        if s.skill and s.skill.name
    }
    student_levels = {
        (s.skill.name if s.skill else "").strip(): max(1, min(5, int(s.level or 1)))
        for s in StudentSkill.query.filter_by(student_id=profile.id).all()
        if s.skill and s.skill.name
    }

    required = structured["skills_required"]
    preferred = structured["skills_preferred"]
    matched_required = sorted(set(required) & student_skills)
    missing_required = sorted(set(required) - student_skills)
    matched_preferred = sorted(set(preferred) & student_skills)
    missing_preferred = sorted(set(preferred) - student_skills)

    # Build a synthetic profile document for TF-IDF (no resume file required)
    profile_bits: list[str] = []
    if profile.degree:
        profile_bits.append(str(profile.degree))
    if profile.branch:
        profile_bits.append(str(profile.branch))
    if profile.preferred_roles:
        profile_bits.append(str(profile.preferred_roles))
    for name, level in student_levels.items():
        profile_bits.append(f"{name} level {level}")
    from app.models.experience import Project, Certification, Internship

    for p in Project.query.filter_by(student_id=profile.id).all():
        profile_bits.append(
            " ".join(filter(None, [p.title, p.description, p.tech_stack]))
        )
    for c in Certification.query.filter_by(student_id=profile.id).all():
        profile_bits.append(" ".join(filter(None, [c.name, c.issuer])))
    for intern in Internship.query.filter_by(student_id=profile.id).all():
        profile_bits.append(
            " ".join(filter(None, [intern.title, intern.description, intern.company]))
        )
    profile_text = "\n".join(profile_bits)
    tfidf = tfidf_cosine_match(profile_text, text or "")

    req_overlap = (
        round(len(matched_required) / len(required) * 100.0, 2) if required else 0.0
    )
    # Blend: 55% skill overlap on required, 45% TF-IDF similarity
    combined = round(0.55 * req_overlap + 0.45 * (tfidf * 100.0), 2)

    # Also surface catalog skills detected in JD text via resume_intel helper
    jd_catalog = extract_skills_from_text(text or "")

    return {
        "structured": structured,
        "tfidf_similarity": tfidf,
        "required_overlap_pct": req_overlap,
        "combined_fit_pct": combined,
        "matched_required": matched_required,
        "missing_required": missing_required,
        "matched_preferred": matched_preferred,
        "missing_preferred": missing_preferred,
        "student_skill_levels": student_levels,
        "jd_catalog_skills": [s["name"] for s in jd_catalog],
        "how_calculated": (
            "combined_fit_pct = 0.55 * required_skill_overlap_pct + "
            "0.45 * (tfidf_cosine_similarity * 100); deterministic."
        ),
        "disclaimer": (
            "Educational JD comparison only — not a hiring recommendation."
        ),
    }
