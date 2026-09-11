"""Security helpers: uploads and role gates."""

from __future__ import annotations

import uuid
from functools import wraps
from pathlib import Path
from typing import Callable, Iterable

from flask import abort, current_app, flash, redirect, url_for
from flask_login import current_user
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


def allowed_file(filename: str, allowed: Iterable[str] | None = None) -> bool:
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[-1].lower()
    if allowed is None:
        allowed = current_app.config.get("ALLOWED_RESUME_EXTENSIONS", {"pdf", "docx"})
    return ext in {a.lower() for a in allowed}


def secure_save(file: FileStorage, subdirectory: str = "resumes") -> tuple[str, str, Path]:
    """
    Save an uploaded file under UPLOAD_FOLDER.

    Returns (original_filename, stored_filename, absolute_path).
    """
    if file is None or not file.filename:
        raise ValueError("No file provided.")
    if not allowed_file(file.filename):
        raise ValueError("File type not allowed.")

    original = secure_filename(file.filename)
    ext = original.rsplit(".", 1)[-1].lower()
    stored = f"{uuid.uuid4().hex}.{ext}"

    base = Path(current_app.config["UPLOAD_FOLDER"])
    dest_dir = base / subdirectory
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / stored
    file.save(dest_path)
    return original, stored, dest_path


def role_required(*roles: str) -> Callable:
    """Require authentication and one of the given roles."""

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for(current_app.login_manager.login_view or "auth.login"))
            if roles and current_user.role not in roles:
                flash("You do not have permission to access that page.", "danger")
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
