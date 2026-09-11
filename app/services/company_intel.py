"""Company / dream-role fit analysis with evidence and disclaimers."""

from __future__ import annotations

from typing import Any

from app.models.profile import StudentProfile
from app.models.research import Company, CompanyRoleRequirement, EvidenceSource
from app.models.skills import CareerRole, RoleSkill, StudentSkill
from app.services.career import match_roles, score_role
from app.services.evidence import serialize_evidence
from app.utils.readiness import compute_all_readiness, overall_readiness

DISCLAIMER = (
    "EDUNOVA AI company-role mappings are illustrative educational estimates "
    "derived from public careers pages and catalog skills — not live hiring "
    "requirements or placement guarantees."
)

FIT_LABELS = (
    (80.0, "Strong"),
    (60.0, "Competitive"),
    (40.0, "Developing"),
    (0.0, "Major gap"),
)


def _fit_label(score: float) -> str:
    for threshold, label in FIT_LABELS:
        if score >= threshold:
            return label
    return "Major gap"


def _student_levels(profile: StudentProfile) -> dict[int, int]:
    return {
        int(s.skill_id): max(1, min(5, int(s.level or 1)))
        for s in StudentSkill.query.filter_by(student_id=profile.id).all()
    }


def list_companies() -> list[dict[str, Any]]:
    companies = Company.query.order_by(Company.name.asc()).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "slug": c.slug,
            "company_type": c.company_type,
            "industry": getattr(c, "industry", None),
            "headquarters": getattr(c, "headquarters", None),
            "description": getattr(c, "description", None),
            "competitiveness": getattr(c, "competitiveness", None),
            "website": c.website,
            "careers_url": c.careers_url,
            "country_focus": c.country_focus,
            "notes": c.notes,
        }
        for c in companies
    ]


def _merged_requirements(
    company_id: int, role_id: int
) -> list[dict[str, Any]]:
    """Merge CompanyRoleRequirement rows with RoleSkill catalog for the role."""
    by_skill: dict[int, dict[str, Any]] = {}

    for rs in RoleSkill.query.filter_by(role_id=role_id).all():
        by_skill[int(rs.skill_id)] = {
            "skill_id": rs.skill_id,
            "skill_name": rs.skill.name if rs.skill else f"skill#{rs.skill_id}",
            "required_level": max(1, min(5, int(rs.required_level or 1))),
            "importance": "important",
            "importance_weight": float(rs.importance or 1.0),
            "source": "role_catalog",
            "evidence_source_id": None,
            "requirement_text": None,
        }

    company_reqs = CompanyRoleRequirement.query.filter_by(
        company_id=company_id, career_role_id=role_id
    ).all()
    for req in company_reqs:
        if req.skill_id is None:
            continue
        sid = int(req.skill_id)
        entry = by_skill.get(sid, {
            "skill_id": sid,
            "skill_name": req.skill.name if req.skill else f"skill#{sid}",
            "required_level": 3,
            "importance": "important",
            "importance_weight": 1.0,
            "source": "company",
            "evidence_source_id": None,
            "requirement_text": None,
        })
        entry["required_level"] = max(
            1, min(5, int(req.required_level or entry["required_level"]))
        )
        entry["importance"] = req.importance or entry["importance"]
        # Map string importance to weight if only company source
        weight_map = {
            "core": 1.5,
            "important": 1.2,
            "supporting": 1.0,
            "nice": 0.7,
        }
        entry["importance_weight"] = weight_map.get(
            (req.importance or "important").lower(),
            entry.get("importance_weight", 1.0),
        )
        entry["source"] = "company+catalog" if sid in by_skill else "company"
        entry["evidence_source_id"] = req.evidence_source_id
        entry["requirement_text"] = req.requirement_text
        entry["title"] = req.title
        entry["location"] = req.location
        entry["seniority"] = req.seniority
        by_skill[sid] = entry

    return list(by_skill.values())


def _fit_from_requirements(
    student_levels: dict[int, int], requirements: list[dict[str, Any]]
) -> dict[str, Any]:
    if not requirements:
        return {
            "fit_pct": 0.0,
            "missing_skills": [],
            "met_skills": [],
            "earned": 0.0,
            "maximum": 0.0,
        }

    missing: list[dict[str, Any]] = []
    met: list[dict[str, Any]] = []
    earned = 0.0
    maximum = 0.0

    for req in requirements:
        required = int(req["required_level"])
        weight = float(req.get("importance_weight") or 1.0)
        maximum += weight * required
        have = student_levels.get(int(req["skill_id"]), 0)
        item = {
            **req,
            "current_level": have,
            "gap": max(0, required - have),
        }
        if have >= required:
            earned += weight * required
            met.append(item)
        else:
            earned += weight * have
            missing.append(item)

    fit_pct = round((earned / maximum) * 100.0, 2) if maximum > 0 else 0.0
    missing.sort(key=lambda m: (-m["gap"], m["skill_name"]))
    met.sort(key=lambda m: m["skill_name"])
    return {
        "fit_pct": fit_pct,
        "missing_skills": missing,
        "met_skills": met,
        "earned": round(earned, 4),
        "maximum": round(maximum, 4),
    }


def dream_company_analysis(
    profile: StudentProfile,
    company_id: int,
    role_id: int,
) -> dict[str, Any]:
    company = Company.query.get(company_id)
    role = CareerRole.query.get(role_id)
    if company is None or role is None:
        return {
            "error": "company_or_role_not_found",
            "disclaimer": DISCLAIMER,
        }

    student_levels = _student_levels(profile)
    requirements = _merged_requirements(company_id, role_id)
    fit = _fit_from_requirements(student_levels, requirements)
    role_score = score_role(role, student_levels)
    readiness = compute_all_readiness(profile)
    current_overall = overall_readiness(profile)

    # Target scores: assume meeting all required levels → 85 readiness-like target
    target_skill = 85.0
    target_overall = 80.0
    distance = {
        "current_fit_pct": fit["fit_pct"],
        "target_fit_pct": 100.0,
        "fit_gap": round(100.0 - fit["fit_pct"], 2),
        "current_overall_readiness": current_overall,
        "target_overall_readiness": target_overall,
        "readiness_gap": round(max(0.0, target_overall - current_overall), 2),
        "current_role_match_pct": role_score["match_pct"],
        "target_skill_readiness": target_skill,
    }

    evidence_ids = {
        r["evidence_source_id"]
        for r in requirements
        if r.get("evidence_source_id")
    }
    # Also attach company careers page as evidence if stored
    evidence_list: list[dict[str, Any]] = []
    for eid in sorted(evidence_ids):
        src = EvidenceSource.query.get(eid)
        ser = serialize_evidence(src)
        if ser:
            evidence_list.append(ser)

    if company.careers_url:
        evidence_list.append(
            {
                "title": f"{company.name} Careers",
                "url": company.careers_url,
                "source_type": "official_careers",
                "publisher": company.name,
                "is_official": True,
                "verification_status": "verified",
                "notes": "Public careers portal — not a live JD snapshot.",
            }
        )

    dimensions = {
        "skill_fit": fit["fit_pct"],
        "catalog_role_match": role_score["match_pct"],
        "academic": readiness["academic"],
        "projects": readiness["project"],
        "experience": readiness["experience"],
        "overall_readiness": current_overall,
    }

    return {
        "company": {
            "id": company.id,
            "name": company.name,
            "slug": company.slug,
            "company_type": company.company_type,
            "careers_url": company.careers_url,
        },
        "role": {"id": role.id, "name": role.name, "category": role.category},
        "fit_dimensions": dimensions,
        "fit_label": _fit_label(fit["fit_pct"]),
        "missing_skills": fit["missing_skills"],
        "met_skills": fit["met_skills"],
        "evidence": evidence_list,
        "distance_to_goal": distance,
        "disclaimer": DISCLAIMER,
    }


def opportunity_fit(profile: StudentProfile) -> dict[str, Any]:
    """Rank company–role pairs with Strong/Competitive/Developing/Major gap."""
    student_levels = _student_levels(profile)
    companies = Company.query.order_by(Company.name.asc()).all()
    pairs: list[dict[str, Any]] = []

    # Prefer roles that have CompanyRoleRequirement rows; else top catalog matches
    top_roles = match_roles(profile, limit=5)
    role_ids = {int(r["role_id"]) for r in top_roles}

    for company in companies:
        company_role_ids = {
            int(r.career_role_id)
            for r in CompanyRoleRequirement.query.filter_by(company_id=company.id)
            .with_entities(CompanyRoleRequirement.career_role_id)
            .distinct()
        }
        candidate_roles = company_role_ids or role_ids
        for rid in candidate_roles:
            role = CareerRole.query.get(rid)
            if role is None:
                continue
            requirements = _merged_requirements(company.id, rid)
            fit = _fit_from_requirements(student_levels, requirements)
            pairs.append(
                {
                    "company_id": company.id,
                    "company_name": company.name,
                    "role_id": role.id,
                    "role_name": role.name,
                    "fit_pct": fit["fit_pct"],
                    "label": _fit_label(fit["fit_pct"]),
                    "missing_count": len(fit["missing_skills"]),
                    "careers_url": company.careers_url,
                }
            )

    pairs.sort(key=lambda p: (-p["fit_pct"], p["company_name"], p["role_name"]))
    return {
        "opportunities": pairs,
        "count": len(pairs),
        "disclaimer": DISCLAIMER,
    }
