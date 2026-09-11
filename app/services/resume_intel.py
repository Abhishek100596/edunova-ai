"""Resume parsing, skill extraction, completeness, and JD matching."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.extensions import db
from app.models.resume import JobDescription, Resume, ResumeAnalysis, ResumeJobMatch
from app.models.skills import Skill

SECTION_PATTERNS = {
    "education": re.compile(r"\b(education|academic|university|college|degree)\b", re.I),
    "experience": re.compile(
        r"\b(experience|employment|work history|internship|intern)\b", re.I
    ),
    "projects": re.compile(r"\b(projects?|portfolio)\b", re.I),
    "skills": re.compile(r"\b(skills?|technologies|tech stack|competenc)\b", re.I),
    "certifications": re.compile(r"\b(certifications?|certificates?|licensed?)\b", re.I),
    "contact": re.compile(
        r"(\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b|\+?\d[\d\s\-()]{7,})",
        re.I,
    ),
}


def extract_text_from_pdf(path: Path) -> str:
    from PyPDF2 import PdfReader

    reader = PdfReader(str(path))
    chunks: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            chunks.append(text)
    return "\n".join(chunks).strip()


def extract_text_from_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    parts = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    return "\n".join(parts).strip()


def extract_text(path: Path, file_ext: str | None = None) -> str:
    ext = (file_ext or path.suffix.lstrip(".")).lower()
    if ext == "pdf":
        return extract_text_from_pdf(path)
    if ext == "docx":
        return extract_text_from_docx(path)
    raise ValueError(f"Unsupported resume extension: {ext!r}")


def extract_skills_from_text(text: str) -> list[dict[str, Any]]:
    """Keyword match resume text against Skill table names (case-insensitive)."""
    if not text:
        return []
    text_l = text.lower()
    found: list[dict[str, Any]] = []
    for skill in Skill.query.order_by(Skill.name.asc()).all():
        name = (skill.name or "").strip()
        if not name:
            continue
        # Word-boundary-ish match so "java" does not match "javascript" wrongly
        # when names differ; allow multi-word skills as substrings.
        pattern = re.compile(
            r"(?<![a-z0-9])" + re.escape(name.lower()) + r"(?![a-z0-9])",
            re.I,
        )
        if pattern.search(text_l):
            found.append(
                {
                    "skill_id": skill.id,
                    "name": skill.name,
                    "category": skill.category,
                }
            )
    return found


def completeness_score(text: str, skills_found: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic completeness 0–100 from section presence and length."""
    sections_present: list[str] = []
    for key, pattern in SECTION_PATTERNS.items():
        if pattern.search(text or ""):
            sections_present.append(key)

    word_count = len(re.findall(r"\b\w+\b", text or ""))
    section_score = (len(sections_present) / max(1, len(SECTION_PATTERNS))) * 60.0
    length_score = min(25.0, (word_count / 400.0) * 25.0)
    skill_score = min(15.0, len(skills_found) * 1.5)
    total = round(min(100.0, section_score + length_score + skill_score), 2)
    return {
        "completeness_score": total,
        "sections_present": sections_present,
        "word_count": word_count,
    }


def improvement_suggestions(
    text: str,
    skills_found: list[dict[str, Any]],
    sections_present: list[str],
) -> list[str]:
    """Suggestions based only on missing structure — never invent experience."""
    suggestions: list[str] = []
    present = set(sections_present)
    if "contact" not in present:
        suggestions.append("Add clear contact details (email and phone).")
    if "education" not in present:
        suggestions.append("Include an Education section with degree and college.")
    if "skills" not in present:
        suggestions.append("Add a dedicated Skills section listing tools you already use.")
    if "projects" not in present:
        suggestions.append(
            "Document projects you have completed — do not invent new ones."
        )
    if "experience" not in present:
        suggestions.append(
            "If you have internships or jobs, add an Experience section with real roles only."
        )
    if "certifications" not in present:
        suggestions.append(
            "List only certifications you actually hold; skip this section if none."
        )
    if len(skills_found) < 5:
        suggestions.append(
            "Expand your skills list with technologies already evidenced in your resume text."
        )
    words = len(re.findall(r"\b\w+\b", text or ""))
    if words < 200:
        suggestions.append(
            "Your resume is quite short; add measurable outcomes for work you already did."
        )
    if not suggestions:
        suggestions.append(
            "Structure looks solid — quantify impact on existing projects without fabricating claims."
        )
    return suggestions


ACTION_VERBS = (
    "built",
    "developed",
    "designed",
    "implemented",
    "analyzed",
    "improved",
    "led",
    "created",
    "optimized",
    "automated",
    "delivered",
    "reduced",
    "increased",
)


def ats_style_analysis(
    text: str,
    skills_found: list[dict[str, Any]],
    sections_present: list[str],
    *,
    target_role_skills: list[str] | None = None,
) -> dict[str, Any]:
    """
    Deterministic ATS-style heuristics — not a claim about any vendor ATS.
    """
    text_l = (text or "").lower()
    words = re.findall(r"\b\w+\b", text_l)
    word_count = len(words)
    present = set(sections_present)

    structure = round((len(present) / max(1, len(SECTION_PATTERNS))) * 100.0, 1)
    verb_hits = sum(1 for v in ACTION_VERBS if re.search(rf"\b{v}\b", text_l))
    action_score = round(min(100.0, verb_hits * 12.0), 1)
    quant_hits = len(re.findall(r"\b\d+%|\b\d+\+|\$\d+|\b\d{2,}\b", text or ""))
    impact_score = round(min(100.0, quant_hits * 10.0 + 20.0), 1)
    length_score = 100.0 if 250 <= word_count <= 900 else (70.0 if 150 <= word_count < 250 or 900 < word_count <= 1200 else 45.0)

    role_match = None
    missing_keywords: list[str] = []
    if target_role_skills:
        found_names = {s["name"].lower() for s in skills_found}
        matched = [s for s in target_role_skills if s.lower() in found_names or s.lower() in text_l]
        missing_keywords = [s for s in target_role_skills if s.lower() not in found_names]
        role_match = round((len(matched) / max(1, len(target_role_skills))) * 100.0, 1)

    ats_ready = round(
        0.35 * structure
        + 0.20 * action_score
        + 0.20 * impact_score
        + 0.15 * length_score
        + 0.10 * min(100.0, len(skills_found) * 8.0),
        1,
    )
    overall = round(
        0.45 * ats_ready
        + 0.35 * (role_match if role_match is not None else structure)
        + 0.20 * min(100.0, len(skills_found) * 6.0),
        1,
    )

    strengths: list[str] = []
    improve: list[str] = []
    if len(skills_found) >= 6:
        strengths.append("Solid catalog skill coverage detected in text.")
    if "projects" in present:
        strengths.append("Projects section present.")
    if action_score >= 60:
        strengths.append("Multiple action verbs detected.")
    if impact_score < 50:
        improve.append("Add measurable project outcomes (numbers you actually achieved).")
    if missing_keywords:
        improve.append(
            "Role keywords not yet evidenced: " + ", ".join(missing_keywords[:8])
        )
    if "skills" not in present:
        improve.append("Add a clear Skills section for ATS-style keyword scanning.")
    if not improve:
        improve.append("Quantify existing achievements without inventing new claims.")

    return {
        "label": "ATS-style analysis (heuristic — not a proprietary ATS)",
        "overall": overall,
        "ats_style_readiness": ats_ready,
        "role_match_pct": role_match,
        "structure_score": structure,
        "action_verb_score": action_score,
        "impact_signal_score": impact_score,
        "length_score": length_score,
        "word_count": word_count,
        "strengths": strengths,
        "improve": improve,
        "missing_keywords": missing_keywords[:15],
        "next_action": (
            improve[0] if improve else "Keep resume aligned with your target role keywords."
        ),
    }


def build_resume_intelligence_report(
    analysis: ResumeAnalysis,
    *,
    target_role_skills: list[str] | None = None,
    resume_text: str = "",
) -> dict[str, Any]:
    try:
        skills = json.loads(analysis.skills_found or "[]")
    except json.JSONDecodeError:
        skills = []
    skill_dicts = [{"name": s} if isinstance(s, str) else s for s in skills]
    try:
        sections = json.loads(analysis.sections_present or "[]")
    except json.JSONDecodeError:
        sections = []
    if isinstance(sections, dict):
        sections_list = [k for k, v in sections.items() if v]
    else:
        sections_list = list(sections)
    report = ats_style_analysis(
        resume_text,
        skill_dicts,
        sections_list,
        target_role_skills=target_role_skills,
    )
    report["completeness_score"] = float(analysis.completeness_score or 0.0)
    return report


def analyze_resume(resume: Resume, file_path: Path | None = None) -> ResumeAnalysis:
    """Parse file if needed, extract skills, score completeness, store analysis."""
    text = resume.parsed_text or ""
    if not text and file_path is not None:
        text = extract_text(file_path, resume.file_ext)
        resume.parsed_text = text

    skills = extract_skills_from_text(text)
    completeness = completeness_score(text, skills)
    suggestions = improvement_suggestions(
        text, skills, completeness["sections_present"]
    )
    report = ats_style_analysis(text, skills, completeness["sections_present"])
    suggestions = [
        f"Overall resume intelligence (heuristic): {report['overall']}/100",
        f"ATS-style readiness: {report['ats_style_readiness']}/100",
        *suggestions,
        *[f"Improve: {x}" for x in report["improve"][:3]],
    ]

    analysis = ResumeAnalysis(
        resume_id=resume.id,
        completeness_score=completeness["completeness_score"],
        skills_found=json.dumps([s["name"] for s in skills]),
        sections_present=json.dumps(completeness["sections_present"]),
        suggestions=json.dumps(suggestions),
        word_count=completeness["word_count"],
    )
    db.session.add(analysis)
    db.session.commit()
    return analysis


def tfidf_cosine_match(resume_text: str, jd_text: str) -> float:
    """TF-IDF cosine similarity via sklearn; deterministic for fixed inputs."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    a = (resume_text or "").strip()
    b = (jd_text or "").strip()
    if not a or not b:
        return 0.0
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    matrix = vectorizer.fit_transform([a, b])
    sim = float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])
    return round(max(0.0, min(1.0, sim)), 4)


def match_resume_to_jd(
    resume: Resume, jd: JobDescription
) -> ResumeJobMatch:
    resume_text = resume.parsed_text or ""
    jd_text = jd.raw_text or ""
    score = tfidf_cosine_match(resume_text, jd_text)

    resume_skills = {s["name"].lower(): s for s in extract_skills_from_text(resume_text)}
    jd_skills = {s["name"].lower(): s for s in extract_skills_from_text(jd_text)}

    matched = sorted(set(resume_skills) & set(jd_skills))
    missing = sorted(set(jd_skills) - set(resume_skills))

    notes_parts = [
        f"TF-IDF cosine similarity: {score:.2%}.",
        "Suggestions are based only on text overlap and catalog skills — "
        "do not fabricate experience to close gaps.",
    ]
    if missing:
        notes_parts.append(
            "Skills mentioned in the JD but not detected in the resume: "
            + ", ".join(jd_skills[m]["name"] for m in missing[:15])
            + "."
        )

    match = ResumeJobMatch(
        resume_id=resume.id,
        job_description_id=jd.id,
        match_score=round(score * 100.0, 2),
        matched_skills=json.dumps([resume_skills[m]["name"] for m in matched]),
        missing_skills=json.dumps([jd_skills[m]["name"] for m in missing]),
        notes=" ".join(notes_parts),
    )
    db.session.add(match)
    db.session.commit()
    return match
