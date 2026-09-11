"""Side-by-side career and company comparisons for a student profile."""

from __future__ import annotations

from typing import Any

from app.models.profile import StudentProfile
from app.models.research import Company
from app.models.skills import CareerRole
from app.services.career import match_roles, score_role
from app.services.company_intel import (
    DISCLAIMER,
    dream_company_analysis,
    _fit_label,
    _merged_requirements,
    _fit_from_requirements,
    _student_levels,
)


def compare_careers(
    profile: StudentProfile, role_id_a: int, role_id_b: int
) -> dict[str, Any]:
    role_a = CareerRole.query.get(role_id_a)
    role_b = CareerRole.query.get(role_id_b)
    if role_a is None or role_b is None:
        return {"error": "role_not_found", "disclaimer": DISCLAIMER}

    levels = _student_levels(profile)
    score_a = score_role(role_a, levels)
    score_b = score_role(role_b, levels)

    gap_names_a = {g["skill_name"] for g in score_a["gaps"]}
    gap_names_b = {g["skill_name"] for g in score_b["gaps"]}
    shared_gaps = sorted(gap_names_a & gap_names_b)
    unique_a = sorted(gap_names_a - gap_names_b)
    unique_b = sorted(gap_names_b - gap_names_a)

    strength_a = {s["skill_name"] for s in score_a["strengths"]}
    strength_b = {s["skill_name"] for s in score_b["strengths"]}

    better = None
    if score_a["match_pct"] > score_b["match_pct"]:
        better = role_a.name
    elif score_b["match_pct"] > score_a["match_pct"]:
        better = role_b.name

    return {
        "role_a": score_a,
        "role_b": score_b,
        "delta_match_pct": round(score_a["match_pct"] - score_b["match_pct"], 2),
        "better_current_fit": better,
        "shared_gap_skills": shared_gaps,
        "unique_gaps_a": unique_a,
        "unique_gaps_b": unique_b,
        "shared_strength_skills": sorted(strength_a & strength_b),
        "disclaimer": DISCLAIMER,
    }


def compare_companies(
    profile: StudentProfile, company_id_a: int, company_id_b: int
) -> dict[str, Any]:
    company_a = Company.query.get(company_id_a)
    company_b = Company.query.get(company_id_b)
    if company_a is None or company_b is None:
        return {"error": "company_not_found", "disclaimer": DISCLAIMER}

    levels = _student_levels(profile)
    # Prefer student's top preferred role names if any; else best catalog match per company
    top = match_roles(profile, limit=1)
    preferred_role_id = int(top[0]["role_id"]) if top else None

    def _company_summary(company: Company, role_id: int | None) -> dict[str, Any]:
        if role_id is None:
            return {
                "company_id": company.id,
                "company_name": company.name,
                "fit_pct": 0.0,
                "label": "Major gap",
                "role_id": None,
                "role_name": None,
                "missing_count": 0,
                "careers_url": company.careers_url,
            }
        role = CareerRole.query.get(role_id)
        reqs = _merged_requirements(company.id, role_id)
        fit = _fit_from_requirements(levels, reqs)
        return {
            "company_id": company.id,
            "company_name": company.name,
            "company_type": company.company_type,
            "fit_pct": fit["fit_pct"],
            "label": _fit_label(fit["fit_pct"]),
            "role_id": role_id,
            "role_name": role.name if role else None,
            "missing_count": len(fit["missing_skills"]),
            "missing_skills": [
                m["skill_name"] for m in fit["missing_skills"][:10]
            ],
            "careers_url": company.careers_url,
        }

    summary_a = _company_summary(company_a, preferred_role_id)
    summary_b = _company_summary(company_b, preferred_role_id)

    better = None
    if summary_a["fit_pct"] > summary_b["fit_pct"]:
        better = company_a.name
    elif summary_b["fit_pct"] > summary_a["fit_pct"]:
        better = company_b.name

    detail_a = (
        dream_company_analysis(profile, company_id_a, preferred_role_id)
        if preferred_role_id
        else None
    )
    detail_b = (
        dream_company_analysis(profile, company_id_b, preferred_role_id)
        if preferred_role_id
        else None
    )

    return {
        "compared_role_id": preferred_role_id,
        "company_a": summary_a,
        "company_b": summary_b,
        "delta_fit_pct": round(summary_a["fit_pct"] - summary_b["fit_pct"], 2),
        "better_current_fit": better,
        "detail_a": detail_a,
        "detail_b": detail_b,
        "disclaimer": DISCLAIMER,
    }
