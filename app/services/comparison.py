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


def _skill_names(items: list[Any] | None, *, limit: int = 12) -> list[str]:
    names: list[str] = []
    for item in items or []:
        if isinstance(item, dict):
            name = item.get("skill_name") or item.get("name")
            if name:
                names.append(str(name))
        elif item:
            names.append(str(item))
        if len(names) >= limit:
            break
    return names


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

    summary = (
        f"Based on your current profile, your calculated fit for "
        f"{role_a.name} is {score_a['match_pct']:.0f}%, while your calculated fit for "
        f"{role_b.name} is {score_b['match_pct']:.0f}%."
    )
    if better:
        summary += f" Right now, {better} is the stronger catalog match."
    if shared_gaps:
        summary += (
            " Shared skill gaps for both roles include: "
            + ", ".join(shared_gaps[:6])
            + "."
        )

    return {
        "role_a": score_a,
        "role_b": score_b,
        "delta_match_pct": round(score_a["match_pct"] - score_b["match_pct"], 2),
        "better_current_fit": better,
        "shared_gap_skills": shared_gaps,
        "unique_gaps_a": unique_a,
        "unique_gaps_b": unique_b,
        "shared_strength_skills": sorted(strength_a & strength_b),
        "summary": summary,
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
    top = match_roles(profile, limit=1)
    preferred_role_id = int(top[0]["role_id"]) if top else None

    def _company_card(company: Company, role_id: int | None) -> dict[str, Any]:
        if role_id is None:
            return {
                "company_id": company.id,
                "company_name": company.name,
                "company_type": company.company_type,
                "fit_pct": 0.0,
                "label": "Major gap",
                "role_id": None,
                "role_name": None,
                "matching_skills": [],
                "missing_skills": [],
                "relevant_requirements": [],
                "careers_url": company.careers_url,
                "career_notes": "Add skills and a preferred role so company fit can be calculated.",
            }
        role = CareerRole.query.get(role_id)
        reqs = _merged_requirements(company.id, role_id)
        fit = _fit_from_requirements(levels, reqs)
        matching = _skill_names(fit.get("met_skills"), limit=12)
        missing = _skill_names(fit.get("missing_skills"), limit=12)
        relevant = []
        for req in reqs[:8]:
            text = req.get("requirement_text") or req.get("skill_name")
            if text:
                relevant.append(str(text))
        return {
            "company_id": company.id,
            "company_name": company.name,
            "company_type": company.company_type,
            "fit_pct": fit["fit_pct"],
            "label": _fit_label(fit["fit_pct"]),
            "role_id": role_id,
            "role_name": role.name if role else None,
            "matching_skills": matching,
            "missing_skills": missing,
            "missing_count": len(fit["missing_skills"]),
            "relevant_requirements": relevant,
            "careers_url": company.careers_url,
            "career_notes": (
                f"Educational compatibility estimate for {role.name if role else 'selected role'} "
                f"using catalog and company requirement maps."
            ),
        }

    summary_a = _company_card(company_a, preferred_role_id)
    summary_b = _company_card(company_b, preferred_role_id)

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

    # Prefer richer skill lists from dream analysis when available.
    for summary, detail in ((summary_a, detail_a), (summary_b, detail_b)):
        if not detail or detail.get("error"):
            continue
        if detail.get("met_skills"):
            summary["matching_skills"] = _skill_names(detail["met_skills"], limit=12)
        if detail.get("missing_skills"):
            summary["missing_skills"] = _skill_names(detail["missing_skills"], limit=12)

    role_label = summary_a.get("role_name") or summary_b.get("role_name") or "your target role"
    summary = (
        f"Based on your current profile, your calculated fit for "
        f"{company_a.name} is {summary_a['fit_pct']:.0f}%, while your calculated fit for "
        f"{company_b.name} is {summary_b['fit_pct']:.0f}% "
        f"(compared against {role_label})."
    )
    if better:
        summary += f" {better} currently shows the stronger educational fit."
    miss_a = set(summary_a.get("missing_skills") or [])
    miss_b = set(summary_b.get("missing_skills") or [])
    shared_missing = sorted(miss_a & miss_b)
    if shared_missing:
        summary += (
            " Skills that appear as gaps for both companies include: "
            + ", ".join(shared_missing[:6])
            + "."
        )
    only_a = sorted(miss_a - miss_b)
    only_b = sorted(miss_b - miss_a)
    if only_a:
        summary += f" Unique gaps for {company_a.name}: " + ", ".join(only_a[:4]) + "."
    if only_b:
        summary += f" Unique gaps for {company_b.name}: " + ", ".join(only_b[:4]) + "."

    return {
        "compared_role_id": preferred_role_id,
        "compared_role_name": role_label if preferred_role_id else None,
        "company_a": summary_a,
        "company_b": summary_b,
        "delta_fit_pct": round(summary_a["fit_pct"] - summary_b["fit_pct"], 2),
        "better_current_fit": better,
        "summary": summary,
        "detail_a": detail_a,
        "detail_b": detail_b,
        "disclaimer": DISCLAIMER,
    }
