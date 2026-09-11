"""Admin dashboard and catalog management (admin role only)."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import FloatField, IntegerField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.extensions import db
from app.models import (
    CareerRole,
    PredictionRecord,
    RoleSkill,
    Skill,
    StudentProfile,
    User,
)

try:
    from app.models import Company, EvidenceSource
except ImportError:  # pragma: no cover
    Company = None  # type: ignore
    EvidenceSource = None  # type: ignore
from app.routes import admin_required

bp = Blueprint("admin", __name__)


class SkillForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(1, 120)])
    category = StringField("Category", validators=[Optional(), Length(0, 80)])
    submit = SubmitField("Save skill")


class RoleForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(1, 160)])
    category = StringField("Category", validators=[Optional(), Length(0, 80)])
    description = TextAreaField("Description", validators=[Optional(), Length(0, 5000)])
    submit = SubmitField("Save role")


class RoleSkillForm(FlaskForm):
    skill_id = IntegerField("Skill id", validators=[DataRequired()])
    required_level = IntegerField(
        "Required level", validators=[DataRequired(), NumberRange(1, 5)]
    )
    importance = FloatField(
        "Importance", validators=[Optional(), NumberRange(0.1, 5.0)]
    )
    submit = SubmitField("Add requirement")


@bp.before_request
@admin_required
def _require_admin():
    """Block non-admins from every admin route (including students)."""
    return None


@bp.route("/")
@bp.route("/dashboard")
def dashboard():
    stats = {
        "students": User.query.filter_by(role="student").count(),
        "admins": User.query.filter_by(role="admin").count(),
        "skills": Skill.query.count(),
        "roles": CareerRole.query.count(),
        "profiles": StudentProfile.query.count(),
        "predictions": PredictionRecord.query.count(),
    }
    recent_students = (
        User.query.filter_by(role="student")
        .order_by(User.created_at.desc())
        .limit(8)
        .all()
    )
    return render_template(
        "admin/dashboard.html", stats=stats, recent_students=recent_students
    )


@bp.route("/students")
def students():
    q = request.args.get("q", "").strip()
    query = User.query.filter_by(role="student")
    if q:
        like = f"%{q}%"
        query = query.filter(User.email.ilike(like) | User.name.ilike(like))
    rows = query.order_by(User.created_at.desc()).all()
    return render_template("admin/students.html", students=rows, q=q)


@bp.route("/skills", methods=["GET", "POST"])
def skills():
    form = SkillForm()
    if form.validate_on_submit():
        name = form.name.data.strip()
        existing = Skill.query.filter_by(name=name).first()
        if existing:
            existing.category = form.category.data or existing.category
            flash("Skill updated.", "success")
        else:
            db.session.add(
                Skill(name=name, category=form.category.data or "general")
            )
            flash("Skill created.", "success")
        db.session.commit()
        return redirect(url_for("admin.skills"))
    items = Skill.query.order_by(Skill.category, Skill.name).all()
    return render_template("admin/skills.html", form=form, skills=items)


@bp.route("/roles", methods=["GET", "POST"])
def roles():
    form = RoleForm()
    rs_form = RoleSkillForm()
    if form.validate_on_submit() and "save_role" in request.form:
        name = form.name.data.strip()
        existing = CareerRole.query.filter_by(name=name).first()
        if existing:
            existing.category = form.category.data or existing.category
            existing.description = form.description.data
            flash("Role updated.", "success")
        else:
            db.session.add(
                CareerRole(
                    name=name,
                    category=form.category.data or "general",
                    description=form.description.data,
                )
            )
            flash("Role created.", "success")
        db.session.commit()
        return redirect(url_for("admin.roles"))

    if rs_form.validate_on_submit() and "add_req" in request.form:
        role_id = request.form.get("role_id", type=int)
        role = db.session.get(CareerRole, role_id) if role_id else None
        skill = db.session.get(Skill, rs_form.skill_id.data)
        if role is None or skill is None:
            flash("Invalid role or skill.", "danger")
        else:
            link = RoleSkill.query.filter_by(
                role_id=role.id, skill_id=skill.id
            ).first()
            if link is None:
                db.session.add(
                    RoleSkill(
                        role_id=role.id,
                        skill_id=skill.id,
                        required_level=rs_form.required_level.data,
                        importance=rs_form.importance.data or 1.0,
                    )
                )
            else:
                link.required_level = rs_form.required_level.data
                link.importance = rs_form.importance.data or 1.0
            db.session.commit()
            flash("Role skill requirement saved.", "success")
        return redirect(url_for("admin.roles"))

    items = CareerRole.query.order_by(CareerRole.name).all()
    all_skills = Skill.query.order_by(Skill.name).all()
    return render_template(
        "admin/roles.html",
        form=form,
        rs_form=rs_form,
        roles=items,
        all_skills=all_skills,
    )


@bp.route("/companies")
def companies():
    rows = []
    if Company is not None:
        rows = Company.query.order_by(Company.name).all()
    return render_template("admin/companies.html", companies=rows)


@bp.route("/evidence-sources")
def evidence_sources():
    rows = []
    if EvidenceSource is not None:
        rows = EvidenceSource.query.order_by(
            EvidenceSource.source_priority.desc(), EvidenceSource.title.asc()
        ).all()
    return render_template("admin/evidence_sources.html", sources=rows)
