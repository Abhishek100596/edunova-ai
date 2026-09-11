"""Shared route helpers."""

from __future__ import annotations

import json
from functools import wraps
from typing import Any, Callable

from flask import abort, flash, redirect, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import StudentProfile


def ensure_student_profile() -> StudentProfile:
    """Return the current student's profile, creating an empty one if needed."""
    if not current_user.is_authenticated or not current_user.is_student():
        abort(403)
    profile = StudentProfile.query.filter_by(user_id=current_user.id).first()
    if profile is None:
        profile = StudentProfile(user_id=current_user.id)
        db.session.add(profile)
        db.session.commit()
    return profile


def admin_required(view: Callable) -> Callable:
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin():
            flash("Admin access required.", "danger")
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def student_required(view: Callable) -> Callable:
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_student():
            flash("Student access required.", "danger")
            if current_user.is_admin():
                return redirect(url_for("admin.dashboard"))
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def csv_to_json_list(raw: str | None) -> str:
    if not raw:
        return json.dumps([])
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return json.dumps(parts)


def json_list_to_csv(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return ", ".join(str(x) for x in data)
    except json.JSONDecodeError:
        pass
    return raw


def parse_json(raw: str | None, default: Any = None) -> Any:
    if default is None:
        default = []
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
