"""Authentication routes — register, login, logout."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.forms import LoginForm, RegisterForm
from app.models import Notification, StudentProfile, User

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return _post_login_redirect(current_user)

    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User(email=email, name=form.name.data.strip(), role="student")
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=user.id, onboarding_pct=0))
        db.session.add(
            Notification(
                user_id=user.id,
                title="Welcome to NEXORA AI",
                body="Complete onboarding to unlock personalized insights.",
                category="info",
                link="/student/onboarding",
            )
        )
        db.session.commit()
        login_user(user)
        flash("Account created. Let's finish onboarding.", "success")
        return redirect(url_for("student.onboarding"))
    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return _post_login_redirect(current_user)

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()
        if user is None or not user.check_password(form.password.data):
            flash("Invalid email or password.", "danger")
            return render_template("auth/login.html", form=form), 401
        login_user(user, remember=bool(form.remember.data))
        flash(f"Welcome back, {user.name or user.email}.", "success")
        next_url = request.args.get("next")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return _post_login_redirect(user)
    return render_template("auth/login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("main.index"))


def _post_login_redirect(user: User):
    if user.is_admin():
        return redirect(url_for("admin.dashboard"))
    profile = StudentProfile.query.filter_by(user_id=user.id).first()
    if profile is None or (profile.onboarding_pct or 0) < 100:
        return redirect(url_for("student.onboarding"))
    return redirect(url_for("student.dashboard"))
