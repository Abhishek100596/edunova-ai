"""Student-facing routes for EDUNOVA AI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_login import current_user

from app.extensions import db
from app.forms import (
    AddStudentSkillForm,
    AddTrackedCompanyForm,
    CoachForm,
    InterviewAnswerForm,
    InterviewStartForm,
    JDMatchForm,
    OnboardingAcademicsForm,
    OnboardingPreferencesForm,
    OnboardingSkillsForm,
    ProfileForm,
    ProjectForm,
    ResumeUploadForm,
    RoadmapGenerateForm,
    SkillGapForm,
    TaskStatusForm,
    ThemeForm,
)
from app.models import (
    AIConversation,
    CareerRole,
    Certification,
    Company,
    Internship,
    InterviewQuestion,
    InterviewSession,
    JobDescription,
    LearningRoadmap,
    LearningTask,
    Notification,
    PredictionRecord,
    ProgressRecord,
    Project,
    Resume,
    ResumeAnalysis,
    Skill,
    StudentSkill,
    UserTarget,
)
from app.routes import (
    csv_to_json_list,
    ensure_student_profile,
    json_list_to_csv,
    parse_json,
    student_required,
)
from app.services import career as career_svc
from app.services import coach as coach_svc
from app.services import interview as interview_svc
from app.services import placement as placement_svc
from app.services import resume_intel as resume_svc
from app.services import roadmap as roadmap_svc
from app.services import skill_gap as skill_gap_svc
from app.utils.readiness import readiness_breakdown
from app.utils.security import secure_save
from ml.explainability.explain import explain_prediction

bp = Blueprint("student", __name__)


def _save_prediction(profile, result: dict) -> PredictionRecord:
    record = PredictionRecord(
        student_id=profile.id,
        probability=float(result["probability"]),
        readiness=float(result["readiness"]),
        factors_positive=json.dumps(result.get("factors_positive") or []),
        factors_negative=json.dumps(result.get("factors_negative") or []),
        model_meta=json.dumps(result.get("model_meta") or {}),
    )
    db.session.add(record)
    db.session.add(
        ProgressRecord(
            student_id=profile.id,
            metric_name="readiness",
            metric_value=float(result["readiness"]),
            snapshot=json.dumps(
                {
                    "probability": result["probability"],
                    "components": (result.get("model_meta") or {}).get(
                        "readiness_components"
                    ),
                }
            ),
        )
    )
    db.session.commit()
    return record


@bp.route("/dashboard")
@student_required
def dashboard():
    profile = ensure_student_profile()
    if (profile.onboarding_pct or 0) < 100:
        flash("Complete onboarding to personalize your dashboard.", "warning")
        return redirect(url_for("student.onboarding"))

    latest = (
        PredictionRecord.query.filter_by(student_id=profile.id)
        .order_by(PredictionRecord.created_at.desc())
        .first()
    )
    notifications = (
        Notification.query.filter_by(user_id=current_user.id, is_read=False)
        .order_by(Notification.created_at.desc())
        .limit(5)
        .all()
    )

    try:
        from app.services.personalization import dashboard_intelligence

        intel = dashboard_intelligence(profile)
    except Exception:  # noqa: BLE001
        intel = None

    readiness = (intel or {}).get("readiness") or readiness_breakdown(profile)
    roles = (intel or {}).get("career_matches") or career_svc.match_roles(profile, limit=3)
    intelligence_score = (intel or {}).get("intelligence")
    biggest_gap = None
    if roles:
        gaps = roles[0].get("gaps") or []
        if gaps:
            biggest_gap = gaps[0]

    next_actions = []
    for action in (intel or {}).get("actions") or []:
        endpoint = action.get("href") or "student.prediction"
        try:
            url = url_for(endpoint)
        except Exception:  # noqa: BLE001
            url = url_for("student.prediction")
        next_actions.append(
            {
                "title": action.get("title"),
                "detail": action.get("reason"),
                "url": url,
            }
        )
    if not next_actions:
        next_actions = [
            {
                "title": "Refresh placement prediction",
                "detail": "Update probability with your latest profile signals.",
                "url": url_for("student.prediction"),
            },
            {
                "title": "Review skill intelligence",
                "detail": "See evidence-backed confidence for each skill.",
                "url": url_for("intelligence.skill_intelligence"),
            },
            {
                "title": "Check opportunity fit",
                "detail": "Rank company–role pairs against your profile.",
                "url": url_for("intelligence.opportunity_fit"),
            },
        ]

    return render_template(
        "student/dashboard.html",
        profile=profile,
        latest=latest,
        readiness=readiness,
        top_roles=roles,
        notifications=notifications,
        intelligence_score=intelligence_score,
        biggest_gap=biggest_gap,
        next_actions=next_actions,
        dash=intel,
        opportunities=(intel or {}).get("opportunities") or [],
        history=(intel or {}).get("history") or {},
        disclaimer=(intel or {}).get("disclaimer"),
    )


@bp.route("/onboarding", methods=["GET", "POST"])
@student_required
def onboarding():
    profile = ensure_student_profile()
    step = int(request.args.get("step") or request.form.get("step") or 1)
    step = max(1, min(3, step))

    academics = OnboardingAcademicsForm(prefix="a")
    prefs = OnboardingPreferencesForm(prefix="p")
    skills_form = OnboardingSkillsForm(prefix="s")
    all_skills = Skill.query.order_by(Skill.category, Skill.name).all()

    if request.method == "POST":
        if step == 1 and academics.validate_on_submit():
            profile.college = academics.college.data
            profile.degree = academics.degree.data
            profile.branch = academics.branch.data
            profile.graduation_year = academics.graduation_year.data
            profile.location = academics.location.data
            profile.age = academics.age.data
            profile.cgpa = academics.cgpa.data
            profile.attendance = academics.attendance.data
            profile.backlogs = academics.backlogs.data or 0
            profile.academic_consistency = academics.academic_consistency.data
            profile.onboarding_pct = max(profile.onboarding_pct or 0, 40)
            db.session.commit()
            flash("Academics saved.", "success")
            return redirect(url_for("student.onboarding", step=2))

        if step == 2 and prefs.validate_on_submit():
            profile.preferred_roles = csv_to_json_list(prefs.preferred_roles.data)
            profile.preferred_industries = csv_to_json_list(
                prefs.preferred_industries.data
            )
            profile.target_companies = csv_to_json_list(prefs.target_companies.data)
            profile.preferred_location = prefs.preferred_location.data
            profile.higher_studies = bool(prefs.higher_studies.data)
            profile.onboarding_pct = max(profile.onboarding_pct or 0, 70)
            db.session.commit()
            flash("Preferences saved.", "success")
            return redirect(url_for("student.onboarding", step=3))

        if step == 3 and skills_form.validate_on_submit():
            selected = request.form.getlist("skill_ids")
            for sid in selected:
                try:
                    skill_id = int(sid)
                except ValueError:
                    continue
                level_raw = request.form.get(f"skill_level_{skill_id}", "3")
                try:
                    level = max(1, min(5, int(level_raw)))
                except ValueError:
                    level = 3
                link = StudentSkill.query.filter_by(
                    student_id=profile.id, skill_id=skill_id
                ).first()
                if link is None:
                    db.session.add(
                        StudentSkill(
                            student_id=profile.id, skill_id=skill_id, level=level
                        )
                    )
                else:
                    link.level = level
            profile.onboarding_pct = 100
            db.session.commit()
            flash("Onboarding complete.", "success")
            return redirect(url_for("student.dashboard"))

    # Prefill
    academics.college.data = profile.college
    academics.degree.data = profile.degree
    academics.branch.data = profile.branch
    academics.graduation_year.data = profile.graduation_year
    academics.location.data = profile.location
    academics.age.data = profile.age
    academics.cgpa.data = profile.cgpa
    academics.attendance.data = profile.attendance
    academics.backlogs.data = profile.backlogs
    academics.academic_consistency.data = profile.academic_consistency
    prefs.preferred_roles.data = json_list_to_csv(profile.preferred_roles)
    prefs.preferred_industries.data = json_list_to_csv(profile.preferred_industries)
    prefs.target_companies.data = json_list_to_csv(profile.target_companies)
    prefs.preferred_location.data = profile.preferred_location
    prefs.higher_studies.data = profile.higher_studies

    existing_levels = {
        ss.skill_id: ss.level
        for ss in StudentSkill.query.filter_by(student_id=profile.id).all()
    }
    return render_template(
        "student/onboarding.html",
        step=step,
        academics=academics,
        prefs=prefs,
        skills_form=skills_form,
        all_skills=all_skills,
        existing_levels=existing_levels,
        profile=profile,
    )


@bp.route("/profile", methods=["GET", "POST"])
@student_required
def profile():
    profile = ensure_student_profile()
    form = ProfileForm()
    skill_form = AddStudentSkillForm()

    if request.args.get("remove_skill"):
        try:
            sid = int(request.args.get("remove_skill"))
        except (TypeError, ValueError):
            sid = None
        if sid:
            link = StudentSkill.query.filter_by(
                student_id=profile.id, skill_id=sid
            ).first()
            if link:
                db.session.delete(link)
                db.session.commit()
                flash("Skill removed from your profile.", "success")
        return redirect(url_for("student.profile"))

    if skill_form.validate_on_submit() and "add_skill" in request.form:
        name = skill_form.skill_name.data.strip()
        existing_skill = Skill.query.filter(Skill.name.ilike(name)).first()
        if existing_skill is None:
            existing_skill = Skill(
                name=name,
                category=skill_form.category.data,
                description=skill_form.description.data,
            )
            db.session.add(existing_skill)
            db.session.flush()
        link = StudentSkill.query.filter_by(
            student_id=profile.id, skill_id=existing_skill.id
        ).first()
        if link is not None:
            flash("You already have this skill — level updated.", "info")
            link.level = int(skill_form.level.data)
        else:
            db.session.add(
                StudentSkill(
                    student_id=profile.id,
                    skill_id=existing_skill.id,
                    level=int(skill_form.level.data),
                )
            )
            flash("Skill added.", "success")
        db.session.commit()
        return redirect(url_for("student.profile"))

    if form.validate_on_submit():
        current_user.name = form.name.data.strip()
        profile.college = form.college.data
        profile.degree = form.degree.data
        profile.branch = form.branch.data
        profile.graduation_year = form.graduation_year.data
        profile.location = form.location.data
        profile.age = form.age.data
        profile.cgpa = form.cgpa.data
        profile.attendance = form.attendance.data
        profile.backlogs = form.backlogs.data or 0
        profile.academic_consistency = form.academic_consistency.data
        profile.preferred_roles = csv_to_json_list(form.preferred_roles.data)
        profile.preferred_industries = csv_to_json_list(form.preferred_industries.data)
        profile.target_companies = csv_to_json_list(form.target_companies.data)
        profile.preferred_location = form.preferred_location.data
        profile.higher_studies = bool(form.higher_studies.data)
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("student.profile"))

    if request.method == "GET":
        form.name.data = current_user.name
        form.college.data = profile.college
        form.degree.data = profile.degree
        form.branch.data = profile.branch
        form.graduation_year.data = profile.graduation_year
        form.location.data = profile.location
        form.age.data = profile.age
        form.cgpa.data = profile.cgpa
        form.attendance.data = profile.attendance
        form.backlogs.data = profile.backlogs
        form.academic_consistency.data = profile.academic_consistency
        form.preferred_roles.data = json_list_to_csv(profile.preferred_roles)
        form.preferred_industries.data = json_list_to_csv(profile.preferred_industries)
        form.target_companies.data = json_list_to_csv(profile.target_companies)
        form.preferred_location.data = profile.preferred_location
        form.higher_studies.data = profile.higher_studies

    skills = (
        StudentSkill.query.filter_by(student_id=profile.id)
        .order_by(StudentSkill.level.desc())
        .all()
    )
    return render_template(
        "student/profile.html",
        form=form,
        profile=profile,
        skills=skills,
        skill_form=skill_form,
    )


@bp.route("/prediction", methods=["GET", "POST"])
@student_required
def prediction():
    profile = ensure_student_profile()
    result = None
    if request.method == "POST":
        result = placement_svc.predict_placement(profile)
        _save_prediction(profile, result)
        flash(
            f"Placement probability: {result['probability']:.0%} · "
            f"Readiness: {result['readiness']:.1f}",
            "success",
        )
    else:
        latest = (
            PredictionRecord.query.filter_by(student_id=profile.id)
            .order_by(PredictionRecord.created_at.desc())
            .first()
        )
        if latest:
            result = {
                "probability": latest.probability,
                "readiness": latest.readiness,
                "factors_positive": parse_json(latest.factors_positive, []),
                "factors_negative": parse_json(latest.factors_negative, []),
                "model_meta": parse_json(latest.model_meta, {}),
            }
    history = (
        PredictionRecord.query.filter_by(student_id=profile.id)
        .order_by(PredictionRecord.created_at.desc())
        .limit(10)
        .all()
    )
    return render_template(
        "student/prediction.html", result=result, history=history, profile=profile
    )


@bp.route("/explain")
@student_required
def explain():
    profile = ensure_student_profile()
    features = placement_svc.build_feature_vector(profile)
    model_path = Path(current_app.config["ML_MODEL_PATH"])
    meta_path = Path(current_app.config["ML_META_PATH"])
    explanation = {"positive": [], "negative": []}
    model_name = "fallback"
    if model_path.exists():
        import joblib

        model = joblib.load(model_path)
        means = None
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            model_name = meta.get("algorithm", type(model).__name__)
            # Approximate means from feature importances context if present.
            means = {n: 0.0 for n in features}
            # Use mid-range educational defaults as baseline means.
            means.update(
                {
                    "cgpa": 7.0,
                    "attendance": 80.0,
                    "backlogs": 0.5,
                    "skill_count": 6.0,
                    "avg_skill_level": 3.0,
                    "project_count": 2.0,
                    "internship_count": 1.0,
                    "certification_count": 1.0,
                    "hackathon_count": 1.0,
                }
            )
        explanation = explain_prediction(
            features, model, feature_names=list(features.keys()), feature_means=means
        )
    else:
        # Contribution-style fallback using placement service factors.
        pred = placement_svc.predict_placement(profile)
        explanation = {
            "positive": pred.get("factors_positive") or [],
            "negative": pred.get("factors_negative") or [],
        }
        model_name = (pred.get("model_meta") or {}).get("model_name", "fallback")

    return render_template(
        "student/explain.html",
        features=features,
        explanation=explanation,
        model_name=model_name,
        profile=profile,
    )


@bp.route("/careers")
@student_required
def careers():
    profile = ensure_student_profile()
    matches = career_svc.match_roles(profile)
    return render_template("student/careers.html", matches=matches, profile=profile)


@bp.route("/skill-gap", methods=["GET", "POST"])
@student_required
def skill_gap():
    profile = ensure_student_profile()
    form = SkillGapForm()
    roles = CareerRole.query.order_by(CareerRole.name).all()
    analysis = None
    matrix = None
    if form.validate_on_submit() or request.args.get("role_id"):
        role_id = form.role_id.data or request.args.get("role_id", type=int)
        if role_id:
            try:
                analysis = skill_gap_svc.gaps_for_role_id(profile, int(role_id))
                role = CareerRole.query.get(int(role_id))
                if role is not None:
                    matrix = skill_gap_svc.skill_gap_matrix(profile, role)
                form.role_id.data = int(role_id)
            except ValueError as exc:
                flash(str(exc), "danger")
    return render_template(
        "student/skill_gap.html",
        form=form,
        roles=roles,
        analysis=analysis,
        matrix=matrix,
        profile=profile,
    )


@bp.route("/roadmap", methods=["GET", "POST"])
@student_required
def roadmap():
    profile = ensure_student_profile()
    gen_form = RoadmapGenerateForm()
    task_form = TaskStatusForm()
    roles = CareerRole.query.order_by(CareerRole.name).all()

    if gen_form.validate_on_submit() and "generate" in request.form:
        role = db.session.get(CareerRole, gen_form.role_id.data)
        if role is None:
            flash("Role not found.", "danger")
        else:
            rm = roadmap_svc.generate_roadmap(profile, role, replace_existing=True)
            flash(f"Roadmap generated: {rm.title}", "success")
            return redirect(url_for("student.roadmap", roadmap_id=rm.id))

    if task_form.validate_on_submit() and "update_task" in request.form:
        try:
            task = roadmap_svc.set_task_status(
                task_form.task_id.data, task_form.status.data
            )
            flash(f"Task updated: {task.title}", "success")
            return redirect(
                url_for("student.roadmap", roadmap_id=task.roadmap_id)
            )
        except ValueError as exc:
            flash(str(exc), "danger")

    roadmap_id = request.args.get("roadmap_id", type=int)
    active = None
    if roadmap_id:
        active = db.session.get(LearningRoadmap, roadmap_id)
        if active and active.student_id != profile.id:
            active = None
            flash("Roadmap not found.", "danger")
    if active is None:
        active = (
            LearningRoadmap.query.filter_by(student_id=profile.id)
            .order_by(LearningRoadmap.updated_at.desc())
            .first()
        )

    summary = roadmap_svc.roadmap_summary(active) if active else None
    all_maps = (
        LearningRoadmap.query.filter_by(student_id=profile.id)
        .order_by(LearningRoadmap.updated_at.desc())
        .all()
    )
    return render_template(
        "student/roadmap.html",
        gen_form=gen_form,
        task_form=task_form,
        roles=roles,
        active=active,
        summary=summary,
        all_maps=all_maps,
        profile=profile,
    )


@bp.route("/resume", methods=["GET", "POST"])
@student_required
def resume():
    profile = ensure_student_profile()
    upload_form = ResumeUploadForm()
    jd_form = JDMatchForm()
    analysis = None
    match = None

    if upload_form.validate_on_submit() and upload_form.resume.data:
        try:
            original, stored, path = secure_save(upload_form.resume.data, "resumes")
            ext = original.rsplit(".", 1)[-1].lower()
            resume_row = Resume(
                student_id=profile.id,
                original_filename=original,
                stored_filename=stored,
                file_ext=ext,
            )
            db.session.add(resume_row)
            db.session.commit()
            analysis = resume_svc.analyze_resume(resume_row, path)
            flash(
                f"Resume analyzed — completeness {analysis.completeness_score:.0f}/100.",
                "success",
            )
            jd_form.resume_id.data = resume_row.id
        except ValueError as exc:
            flash(str(exc), "danger")

    if jd_form.validate_on_submit() and "match" in request.form:
        resume_row = db.session.get(Resume, jd_form.resume_id.data)
        if resume_row is None or resume_row.student_id != profile.id:
            flash("Resume not found.", "danger")
        else:
            jd = JobDescription(
                student_id=profile.id,
                title=jd_form.title.data,
                company=jd_form.company.data,
                raw_text=jd_form.raw_text.data,
            )
            db.session.add(jd)
            db.session.commit()
            match = resume_svc.match_resume_to_jd(resume_row, jd)
            flash(f"Match score: {match.match_score:.1f}%", "success")

    resumes = (
        Resume.query.filter_by(student_id=profile.id)
        .order_by(Resume.uploaded_at.desc())
        .all()
    )
    if resumes and not jd_form.resume_id.data:
        jd_form.resume_id.data = resumes[0].id
    latest_analysis = None
    intel_report = None
    if resumes:
        latest_analysis = (
            ResumeAnalysis.query.filter_by(resume_id=resumes[0].id)
            .order_by(ResumeAnalysis.created_at.desc())
            .first()
        )
        if latest_analysis:
            target_skills = []
            matches = career_svc.match_roles(profile, limit=1)
            if matches:
                target_skills = [
                    g["skill_name"] for g in (matches[0].get("gaps") or [])[:8]
                ] + [
                    s["skill_name"] for s in (matches[0].get("strengths") or [])[:8]
                ]
            intel_report = resume_svc.build_resume_intelligence_report(
                latest_analysis,
                target_role_skills=target_skills or None,
                resume_text=resumes[0].parsed_text or "",
            )
    return render_template(
        "student/resume.html",
        upload_form=upload_form,
        jd_form=jd_form,
        resumes=resumes,
        analysis=analysis or latest_analysis,
        match=match,
        profile=profile,
        parse_json=parse_json,
        intel_report=intel_report,
    )


@bp.route("/interview", methods=["GET", "POST"])
@student_required
def interview():
    profile = ensure_student_profile()
    start_form = InterviewStartForm()
    answer_form = InterviewAnswerForm()

    if start_form.validate_on_submit() and "start" in request.form:
        sess = interview_svc.start_session(
            profile,
            start_form.interview_type.data,
            role_focus=start_form.role_focus.data or None,
        )
        flash("Interview started.", "success")
        return redirect(url_for("student.interview", session_id=sess.id))

    if answer_form.validate_on_submit() and "answer" in request.form:
        try:
            interview_svc.submit_answer(
                answer_form.question_id.data, answer_form.answer_text.data
            )
            flash("Answer submitted and scored.", "success")
            q = db.session.get(InterviewQuestion, answer_form.question_id.data)
            sid = q.session_id if q else request.args.get("session_id", type=int)
            return redirect(url_for("student.interview", session_id=sid))
        except ValueError as exc:
            flash(str(exc), "danger")

    session_id = request.args.get("session_id", type=int)
    detail = None
    if session_id:
        sess = db.session.get(InterviewSession, session_id)
        if sess and sess.student_id == profile.id:
            detail = interview_svc.session_detail(session_id)

    if request.method == "POST" and "complete" in request.form and session_id:
        sess = db.session.get(InterviewSession, session_id)
        if sess and sess.student_id == profile.id:
            interview_svc.complete_session(session_id)
            flash("Interview completed.", "success")
            return redirect(url_for("student.interview_results", session_id=session_id))

    past = (
        InterviewSession.query.filter_by(student_id=profile.id)
        .order_by(InterviewSession.started_at.desc())
        .limit(10)
        .all()
    )
    return render_template(
        "student/interview.html",
        start_form=start_form,
        answer_form=answer_form,
        detail=detail,
        past=past,
        profile=profile,
    )


@bp.route("/interview/<int:session_id>/results")
@student_required
def interview_results(session_id: int):
    profile = ensure_student_profile()
    sess = db.session.get(InterviewSession, session_id)
    if sess is None or sess.student_id != profile.id:
        flash("Interview not found.", "danger")
        return redirect(url_for("student.interview"))
    detail = interview_svc.session_detail(session_id)
    followup = interview_svc.coaching_followup(sess) if sess.status == "completed" else None
    return render_template(
        "student/interview_results.html",
        detail=detail,
        followup=followup,
        profile=profile,
    )


@bp.route("/coach", methods=["GET", "POST"])
@student_required
def coach():
    profile = ensure_student_profile()
    form = CoachForm()
    reply = None
    if request.method == "POST" and "clear" in request.form:
        n = coach_svc.clear_conversation(profile)
        flash(f"Cleared {n} conversation messages.", "success")
        return redirect(url_for("student.coach"))
    if form.validate_on_submit():
        result = coach_svc.ask_coach(profile, form.message.data)
        reply = result["reply"]
        flash(f"Coach replied via {result['provider']}.", "info")
        form.message.data = ""
    history = (
        AIConversation.query.filter_by(student_id=profile.id)
        .order_by(AIConversation.created_at.desc())
        .limit(40)
        .all()
    )
    history = list(reversed(history))
    quick_prompts = [
        "What should I learn next?",
        "Am I ready for a Data Analyst role?",
        "Why is my readiness score what it is?",
        "Which company should I target next?",
        "How can I improve my resume?",
    ]
    return render_template(
        "student/coach.html",
        form=form,
        history=history,
        reply=reply,
        profile=profile,
        quick_prompts=quick_prompts,
    )


@bp.route("/projects", methods=["GET", "POST"])
@student_required
def projects():
    profile = ensure_student_profile()
    form = ProjectForm()
    if form.validate_on_submit():
        db.session.add(
            Project(
                student_id=profile.id,
                title=form.title.data.strip(),
                description=form.description.data,
                tech_stack=form.tech_stack.data,
                role=form.role.data,
                url=form.url.data,
            )
        )
        db.session.commit()
        flash("Project added.", "success")
        return redirect(url_for("student.projects"))

    items = (
        Project.query.filter_by(student_id=profile.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    certs = Certification.query.filter_by(student_id=profile.id).all()
    interns = Internship.query.filter_by(student_id=profile.id).all()
    # Catalog recommendations from career role descriptions.
    role_recs = CareerRole.query.order_by(CareerRole.name).limit(5).all()
    return render_template(
        "student/projects.html",
        form=form,
        projects=items,
        certifications=certs,
        internships=interns,
        role_recs=role_recs,
        profile=profile,
    )


@bp.route("/learning")
@student_required
def learning():
    profile = ensure_student_profile()
    maps = (
        LearningRoadmap.query.filter_by(student_id=profile.id)
        .order_by(LearningRoadmap.updated_at.desc())
        .all()
    )
    tasks_done = (
        db.session.query(LearningTask)
        .join(LearningRoadmap)
        .filter(
            LearningRoadmap.student_id == profile.id,
            LearningTask.status == "completed",
        )
        .count()
    )
    return render_template(
        "student/learning.html",
        roadmaps=maps,
        tasks_done=tasks_done,
        profile=profile,
    )


@bp.route("/analytics")
@student_required
def analytics():
    profile = ensure_student_profile()
    preds = (
        PredictionRecord.query.filter_by(student_id=profile.id)
        .order_by(PredictionRecord.created_at.asc())
        .all()
    )
    progress = (
        ProgressRecord.query.filter_by(student_id=profile.id, metric_name="readiness")
        .order_by(ProgressRecord.recorded_at.asc())
        .all()
    )
    readiness = readiness_breakdown(profile)
    return render_template(
        "student/analytics.html",
        predictions=preds,
        progress=progress,
        readiness=readiness,
        profile=profile,
    )


@bp.route("/report")
@student_required
def report():
    """Generate EDUNOVA Personal Career Intelligence Report (PDF)."""
    profile = ensure_student_profile()
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    readiness = readiness_breakdown(profile)
    latest = (
        PredictionRecord.query.filter_by(student_id=profile.id)
        .order_by(PredictionRecord.created_at.desc())
        .first()
    )
    roles = career_svc.match_roles(profile, limit=5)

    intel = None
    try:
        from app.services.intelligence_score import compute_intelligence_score

        intel = compute_intelligence_score(profile)
    except Exception:  # noqa: BLE001
        intel = None

    opp = None
    try:
        from app.services.company_intel import opportunity_fit

        opp = opportunity_fit(profile)
    except Exception:  # noqa: BLE001
        opp = None

    conf_rows = []
    try:
        from app.services.skill_confidence import compute_skill_confidence

        conf_rows = compute_skill_confidence(profile)[:8]
    except Exception:  # noqa: BLE001
        conf_rows = []

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    def new_page_header(title: str) -> float:
        c.showPage()
        y_local = height - 50
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y_local, title)
        return y_local - 28

    y = height - 50
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, "EDUNOVA AI — Personal Career Intelligence Report")
    y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(50, y, "AI-Powered Education, Skill & Career Intelligence")
    y -= 20
    c.drawString(50, y, f"Student: {current_user.name} <{current_user.email}>")
    y -= 14
    c.drawString(
        50,
        y,
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · Mode: Comprehensive",
    )
    y -= 22
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "1. Executive summary")
    y -= 16
    c.setFont("Helvetica", 10)
    overall = readiness["overall"]
    c.drawString(
        50,
        y,
        f"Overall readiness {overall:.1f}/100. Scores are estimates from your stored profile — not hiring guarantees.",
    )
    y -= 20

    if intel:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "2. Intelligence Score")
        y -= 16
        c.setFont("Helvetica", 10)
        c.drawString(50, y, f"Overall intelligence score: {intel.get('overall', 0):.1f}/100")
        y -= 14
        for name, dim in (intel.get("dimensions") or {}).items():
            score_val = dim.get("score") if isinstance(dim, dict) else dim
            c.drawString(60, y, f"{name.replace('_', ' ').title()}: {float(score_val):.1f}")
            y -= 12
            if y < 80:
                y = new_page_header("Intelligence Score (continued)")
        y -= 8

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "3. Readiness breakdown")
    y -= 16
    c.setFont("Helvetica", 10)
    for name, score in readiness["components"].items():
        c.drawString(60, y, f"{name.title()}: {score:.1f}")
        y -= 12
    y -= 10

    if latest:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "4. ML placement estimate (synthetic educational model)")
        y -= 16
        c.setFont("Helvetica", 10)
        c.drawString(
            50,
            y,
            f"Probability: {latest.probability:.0%} · Readiness: {latest.readiness:.1f}",
        )
        y -= 20

    if y < 120:
        y = new_page_header("Career & opportunity")

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "5. Top career matches")
    y -= 16
    c.setFont("Helvetica", 10)
    for m in roles:
        c.drawString(60, y, f"{m['role_name']}: {m['match_pct']:.1f}% catalog match")
        y -= 12
    y -= 10

    if opp and opp.get("opportunities"):
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "6. Current opportunity fit (top 8)")
        y -= 16
        c.setFont("Helvetica", 9)
        for row in opp["opportunities"][:8]:
            line = (
                f"{row['company_name']} · {row['role_name']}: "
                f"{row['fit_pct']:.0f}% ({row['label']})"
            )
            c.drawString(60, y, line[:95])
            y -= 11
            if y < 70:
                y = new_page_header("Opportunity fit (continued)")
                c.setFont("Helvetica", 9)
        y -= 8

    if conf_rows:
        if y < 140:
            y = new_page_header("Skill confidence")
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "7. Skill confidence")
        y -= 16
        c.setFont("Helvetica", 10)
        for row in conf_rows:
            c.drawString(
                60,
                y,
                f"{row['skill']}: L{row['level']} · {row['label']} "
                f"(conf {row['confidence']:.2f})",
            )
            y -= 12
            if y < 70:
                y = new_page_header("Skill confidence (continued)")
                c.setFont("Helvetica", 10)

    if y < 120:
        y = new_page_header("Limitations & evidence notes")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "8. Model limitations")
    y -= 16
    c.setFont("Helvetica", 9)
    for line in (
        "• ML placement model uses a SYNTHETIC educational dataset — not real hiring outcomes.",
        "• Company/role fit is a compatibility estimate from curated catalog + evidence sources.",
        "• AI coach text is recommendation-only; it is not verified external fact.",
        "• Report version: EDUNOVA Career Intelligence Report 2.0",
    ):
        c.drawString(50, y, line)
        y -= 12

    c.showPage()
    c.save()
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="edunova_career_intelligence_report.pdf",
    )


@bp.route("/theme", methods=["GET", "POST"])
@student_required
def theme():
    profile = ensure_student_profile()
    form = ThemeForm()
    if form.validate_on_submit():
        profile.theme_preference = form.theme.data
        db.session.commit()
        session["theme"] = form.theme.data
        flash("Theme updated.", "success")
        return redirect(url_for("student.theme"))
    form.theme.data = profile.theme_preference or "system"
    return render_template("student/theme.html", form=form, profile=profile)


@bp.route("/notifications")
@student_required
def notifications():
    items = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template("student/notifications.html", notifications=items)


@bp.route("/notifications/<int:note_id>/read", methods=["POST"])
@student_required
def mark_notification_read(note_id: int):
    note = db.session.get(Notification, note_id)
    if note and note.user_id == current_user.id:
        note.is_read = True
        db.session.commit()
    return redirect(url_for("student.notifications"))
