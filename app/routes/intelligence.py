"""Student intelligence routes — company fit, what-if, JD, comparisons."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.forms import (
    CareerSwitchForm,
    CompareCareersForm,
    CompareCompaniesForm,
    DreamCompanyForm,
    JDAnalyzerForm,
    WhatIfForm,
)
from app.models import CareerRole, PredictionRecord, Skill
from app.routes import ensure_student_profile, student_required
from app.utils.readiness import readiness_breakdown

bp = Blueprint("intelligence", __name__)

COMPAT_DISCLAIMER = (
    "Compatibility estimate, not a hiring guarantee."
)
SERVICE_MISSING = (
    "This intelligence module is not available yet. Please try again after services load."
)


def _try_import(module: str, attr: str):
    try:
        mod = __import__(f"app.services.{module}", fromlist=[attr])
        return getattr(mod, attr)
    except (ImportError, AttributeError):
        return None


def _flash_import_error(feature: str) -> None:
    flash(
        f"{feature} service is not available yet. {SERVICE_MISSING}",
        "warning",
    )


@bp.route("/skill-intelligence")
@student_required
def skill_intelligence():
    profile = ensure_student_profile()
    compute = _try_import("skill_confidence", "compute_skill_confidence")
    skills = []
    if compute is None:
        _flash_import_error("Skill confidence")
    else:
        try:
            skills = compute(profile)
        except Exception as exc:  # noqa: BLE001 — surface to UI
            flash(f"Could not compute skill confidence: {exc}", "danger")
    return render_template(
        "student/skill_intelligence.html",
        profile=profile,
        skills=skills,
        disclaimer=COMPAT_DISCLAIMER,
    )


@bp.route("/companies", methods=["GET", "POST"])
@student_required
def companies():
    from app.forms import AddTrackedCompanyForm
    from app.models import Company, UserTarget

    profile = ensure_student_profile()
    track_form = AddTrackedCompanyForm()
    list_fn = _try_import("company_intel", "list_companies")
    companies_list = []
    if list_fn is None:
        try:
            companies_list = [
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
                }
                for c in Company.query.order_by(Company.name).all()
            ]
        except Exception:  # noqa: BLE001
            _flash_import_error("Company intelligence")
    else:
        try:
            companies_list = list_fn()
        except Exception as exc:  # noqa: BLE001
            flash(f"Could not list companies: {exc}", "danger")

    q = (request.args.get("q") or "").strip().lower()
    if q:
        companies_list = [
            c
            for c in companies_list
            if q in (c.get("name") or "").lower()
            or q in (c.get("industry") or "").lower()
            or q in (c.get("company_type") or "").lower()
        ]

    if track_form.validate_on_submit():
        company = None
        if track_form.company_id.data:
            company = Company.query.get(int(track_form.company_id.data))
        name = (track_form.company_name.data or (company.name if company else "")).strip()
        if not name:
            flash("Provide a company name or select a catalog company.", "danger")
        else:
            target = None
            if company:
                target = UserTarget.query.filter_by(
                    user_id=current_user.id, company_id=company.id
                ).first()
            if target is None:
                target = UserTarget(user_id=current_user.id)
                db.session.add(target)
            target.company_id = company.id if company else None
            target.company_name = name
            target.target_role = track_form.target_role.data
            target.location = track_form.location.data
            target.status = track_form.status.data
            target.notes = track_form.notes.data
            db.session.commit()
            flash(f"Saved tracking for {name}.", "success")
            return redirect(url_for("intelligence.companies"))

    tracked = UserTarget.query.filter_by(user_id=current_user.id).all()
    return render_template(
        "student/companies.html",
        profile=profile,
        companies=companies_list,
        disclaimer=COMPAT_DISCLAIMER,
        track_form=track_form,
        tracked=tracked,
        q=q,
    )


@bp.route("/opportunity-fit")
@student_required
def opportunity_fit():
    profile = ensure_student_profile()
    fit_fn = _try_import("company_intel", "opportunity_fit")
    rows = []
    if fit_fn is None:
        _flash_import_error("Opportunity fit")
    else:
        try:
            result = fit_fn(profile)
            if isinstance(result, list):
                rows = result
            elif isinstance(result, dict):
                rows = (
                    result.get("rows")
                    or result.get("opportunities")
                    or result.get("items")
                    or []
                )
        except Exception as exc:  # noqa: BLE001
            flash(f"Could not compute opportunity fit: {exc}", "danger")
    return render_template(
        "student/opportunity_fit.html",
        profile=profile,
        opportunities=rows,
        disclaimer=COMPAT_DISCLAIMER,
    )


@bp.route("/dream-company", methods=["GET", "POST"])
@student_required
def dream_company():
    profile = ensure_student_profile()
    form = DreamCompanyForm()
    analysis = None
    companies_list = []
    roles = CareerRole.query.order_by(CareerRole.name).all()

    list_fn = _try_import("company_intel", "list_companies")
    if list_fn:
        try:
            companies_list = list_fn()
        except Exception:  # noqa: BLE001
            companies_list = []
    if not companies_list:
        try:
            from app.models import Company

            companies_list = [
                {"id": c.id, "name": c.name} for c in Company.query.order_by(Company.name)
            ]
        except Exception:  # noqa: BLE001
            companies_list = []

    if form.validate_on_submit():
        analyze = _try_import("company_intel", "dream_company_analysis")
        if analyze is None:
            _flash_import_error("Dream company")
        else:
            try:
                analysis = analyze(profile, form.company_id.data, form.role_id.data)
                # Persist target if model available
                try:
                    from datetime import datetime, timezone

                    from app.models import UserTarget

                    target = UserTarget.query.filter_by(user_id=current_user.id).first()
                    if target is None:
                        target = UserTarget(user_id=current_user.id)
                        db.session.add(target)
                    target.company_id = form.company_id.data
                    target.career_role_id = form.role_id.data
                    target.experience_level = form.experience_level.data
                    target.location = form.location.data
                    target.updated_at = datetime.now(timezone.utc)
                    db.session.commit()
                except Exception:  # noqa: BLE001
                    db.session.rollback()
                flash("Dream company analysis ready.", "success")
            except Exception as exc:  # noqa: BLE001
                flash(f"Analysis failed: {exc}", "danger")

    return render_template(
        "student/dream_company.html",
        form=form,
        profile=profile,
        analysis=analysis,
        companies=companies_list,
        roles=roles,
        disclaimer=COMPAT_DISCLAIMER,
    )


@bp.route("/what-if", methods=["GET", "POST"])
@student_required
def what_if():
    profile = ensure_student_profile()
    form = WhatIfForm()
    result = None
    skill_names = [
        s.name
        for s in Skill.query.order_by(Skill.name).all()
    ]

    if form.validate_on_submit():
        if form.scenario.data == "skill_level":
            sim = _try_import("what_if", "simulate_skill_level_change")
            if sim is None:
                _flash_import_error("What-if")
            elif not form.skill_name.data:
                flash("Provide a skill name for this scenario.", "warning")
            else:
                try:
                    result = sim(
                        profile,
                        form.skill_name.data.strip(),
                        int(form.new_level.data or 3),
                    )
                except Exception as exc:  # noqa: BLE001
                    flash(f"Simulation failed: {exc}", "danger")
        else:
            sim = _try_import("what_if", "simulate_extra_projects")
            if sim is None:
                _flash_import_error("What-if")
            else:
                try:
                    result = sim(profile, int(form.extra_projects.data or 1))
                except Exception as exc:  # noqa: BLE001
                    flash(f"Simulation failed: {exc}", "danger")

    return render_template(
        "student/what_if.html",
        form=form,
        profile=profile,
        result=result,
        skill_names=skill_names,
        disclaimer="Scenario simulation only — does not change your saved profile.",
    )


@bp.route("/compare-careers", methods=["GET", "POST"])
@student_required
def compare_careers():
    profile = ensure_student_profile()
    form = CompareCareersForm()
    comparison = None
    roles = CareerRole.query.order_by(CareerRole.name).all()

    if form.validate_on_submit():
        compare = _try_import("comparison", "compare_careers")
        if compare is None:
            _flash_import_error("Career comparison")
        else:
            try:
                comparison = compare(
                    profile, form.role_id_a.data, form.role_id_b.data
                )
            except Exception as exc:  # noqa: BLE001
                flash(f"Comparison failed: {exc}", "danger")

    return render_template(
        "student/compare_careers.html",
        form=form,
        profile=profile,
        comparison=comparison,
        roles=roles,
        disclaimer=COMPAT_DISCLAIMER,
    )


@bp.route("/compare-companies", methods=["GET", "POST"])
@student_required
def compare_companies():
    profile = ensure_student_profile()
    form = CompareCompaniesForm()
    comparison = None
    companies_list = []
    list_fn = _try_import("company_intel", "list_companies")
    if list_fn:
        try:
            companies_list = list_fn()
        except Exception:  # noqa: BLE001
            companies_list = []
    if not companies_list:
        try:
            from app.models import Company

            companies_list = [
                {"id": c.id, "name": c.name} for c in Company.query.order_by(Company.name)
            ]
        except Exception:  # noqa: BLE001
            companies_list = []

    if form.validate_on_submit():
        compare = _try_import("comparison", "compare_companies")
        if compare is None:
            _flash_import_error("Company comparison")
        else:
            try:
                comparison = compare(
                    profile, form.company_id_a.data, form.company_id_b.data
                )
            except Exception as exc:  # noqa: BLE001
                flash(f"Comparison failed: {exc}", "danger")

    return render_template(
        "student/compare_companies.html",
        form=form,
        profile=profile,
        comparison=comparison,
        companies=companies_list,
        disclaimer=COMPAT_DISCLAIMER,
    )


@bp.route("/jd-analyzer", methods=["GET", "POST"])
@student_required
def jd_analyzer():
    profile = ensure_student_profile()
    form = JDAnalyzerForm()
    structured = None
    comparison = None

    if form.validate_on_submit():
        extract = _try_import("jd_intel", "extract_jd_structured")
        compare = _try_import("jd_intel", "compare_profile_to_jd")
        if extract is None and compare is None:
            _flash_import_error("JD analyzer")
        else:
            try:
                if extract:
                    structured = extract(form.raw_text.data)
                if compare:
                    comparison = compare(profile, form.raw_text.data)
                flash("JD analysis complete.", "success")
            except Exception as exc:  # noqa: BLE001
                flash(f"JD analysis failed: {exc}", "danger")

    return render_template(
        "student/jd_analyzer.html",
        form=form,
        profile=profile,
        structured=structured,
        comparison=comparison,
        disclaimer=COMPAT_DISCLAIMER,
    )


@bp.route("/intelligence-score")
@student_required
def intelligence_score():
    profile = ensure_student_profile()
    compute = _try_import("intelligence_score", "compute_intelligence_score")
    score = None
    if compute is None:
        _flash_import_error("Intelligence score")
    else:
        try:
            score = compute(profile)
        except Exception as exc:  # noqa: BLE001
            flash(f"Could not compute intelligence score: {exc}", "danger")
    return render_template(
        "student/intelligence_score.html",
        profile=profile,
        score=score,
        disclaimer=COMPAT_DISCLAIMER,
    )


@bp.route("/readiness-center")
@student_required
def readiness_center():
    profile = ensure_student_profile()
    readiness = readiness_breakdown(profile)
    latest = (
        PredictionRecord.query.filter_by(student_id=profile.id)
        .order_by(PredictionRecord.created_at.desc())
        .first()
    )
    intel = None
    compute = _try_import("intelligence_score", "compute_intelligence_score")
    if compute:
        try:
            intel = compute(profile)
        except Exception:  # noqa: BLE001
            intel = None
    history = {"points": [], "is_demo_sample": False, "message": "Not enough historical data yet."}
    try:
        from app.services.personalization import get_readiness_history

        history = get_readiness_history(profile)
    except Exception:  # noqa: BLE001
        pass
    return render_template(
        "student/readiness_center.html",
        profile=profile,
        readiness=readiness,
        latest=latest,
        intelligence=intel,
        history=history,
        disclaimer=COMPAT_DISCLAIMER,
    )


@bp.route("/career-switch", methods=["GET", "POST"])
@student_required
def career_switch():
    profile = ensure_student_profile()
    form = CareerSwitchForm()
    roles = CareerRole.query.order_by(CareerRole.name.asc()).all()
    result = None
    if form.validate_on_submit():
        analyze = _try_import("career_switch", "analyze_career_switch")
        if analyze is None:
            _flash_import_error("Career switch")
        else:
            try:
                current_id = form.current_role_id.data
                result = analyze(
                    profile,
                    current_role_id=int(current_id) if current_id else None,
                    target_role_id=int(form.target_role_id.data),
                    current_role_label=form.current_role_label.data or None,
                )
                if result.get("error"):
                    flash(result["error"].replace("_", " "), "danger")
                    result = None
            except Exception as exc:  # noqa: BLE001
                flash(f"Could not analyze career switch: {exc}", "danger")
    return render_template(
        "student/career_switch.html",
        form=form,
        roles=roles,
        result=result,
        profile=profile,
        disclaimer=COMPAT_DISCLAIMER,
    )
