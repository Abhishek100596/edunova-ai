"""EDUNOVA AI Flask application factory (legacy package path Nexora_AI)."""

from pathlib import Path

from flask import Flask

from app.extensions import csrf, db, login_manager
from config import Config


def create_app(config_object=None) -> Flask:
    """Create and configure the Flask application."""
    from datetime import timedelta

    # Load .env for local/dev without overriding already-set process env (Render secrets).
    try:
        from dotenv import load_dotenv

        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
    except Exception:
        pass

    app = Flask(
        __name__,
        instance_relative_config=False,
        static_folder="static",
        template_folder="templates",
    )
    app.config.from_object(config_object or Config)

    # Ensure SQLite parent directory exists for absolute instance paths.
    uri = str(app.config.get("SQLALCHEMY_DATABASE_URI") or "")
    if uri.startswith("sqlite:///") and ":memory:" not in uri:
        db_path = Path(uri.replace("sqlite:///", "", 1))
        if db_path.parent and str(db_path.parent) not in {"", "."}:
            db_path.parent.mkdir(parents=True, exist_ok=True)

    days = int(app.config.get("REMEMBER_COOKIE_DURATION_DAYS") or 14)
    app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=days)
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
        seconds=int(app.config.get("PERMANENT_SESSION_LIFETIME") or 60 * 60 * 24 * 14)
    )

    _ensure_upload_folder(app)
    _init_extensions(app)
    _register_blueprints(app)
    _register_user_loader()

    # Import models so metadata is registered, then create tables.
    # Use importlib so we do not shadow the local Flask `app` variable.
    import importlib

    importlib.import_module("app.models")

    with app.app_context():
        # create_all is additive / idempotent — it does not wipe existing rows.
        db.create_all()
        try:
            from scripts.seed_demo_data import (
                ensure_extra_columns,
                needs_demo_seed,
                seed_into_app,
            )

            ensure_extra_columns(db)
            # Presentation-ready: empty DB + DEMO_MODE seeds catalog automatically.
            # Skip under pytest (TestConfig uses in-memory DB and seeds its own fixtures).
            if (
                app.config.get("DEMO_MODE")
                and not app.config.get("TESTING")
                and needs_demo_seed()
            ):
                stats = seed_into_app()
                app.logger.info("EDUNOVA demo catalog seeded: %s", stats)
        except Exception as exc:
            app.logger.warning("Demo seed skipped: %s", exc)

    _register_error_handlers(app)
    return app


def _register_error_handlers(app: Flask) -> None:
    from flask import jsonify, render_template, request

    def _wants_json() -> bool:
        if request.path.startswith("/api/"):
            return True
        best = request.accept_mimetypes.best_match(["application/json", "text/html"])
        return best == "application/json" and (
            request.accept_mimetypes[best]
            > request.accept_mimetypes["text/html"]
        )

    def _error_response(code: int, title: str, message: str):
        if _wants_json():
            return jsonify({"error": title, "message": message, "status": code}), code
        template = f"errors/{code}.html"
        try:
            return render_template(template, message=message), code
        except Exception:  # noqa: BLE001
            # Fall back to generic pages for codes without dedicated templates
            generic = "errors/500.html" if code >= 500 else "errors/404.html"
            return render_template(generic, message=message), code

    @app.errorhandler(400)
    def bad_request(e):
        return _error_response(
            400,
            "Bad request",
            "That request could not be understood. Please check your input and try again.",
        )

    @app.errorhandler(401)
    def unauthorized(e):
        return _error_response(
            401,
            "Unauthorized",
            "Please sign in to continue.",
        )

    @app.errorhandler(403)
    def forbidden(e):
        return _error_response(
            403,
            "Forbidden",
            "You do not have permission to view this page.",
        )

    @app.errorhandler(404)
    def not_found(e):
        return _error_response(
            404,
            "Not found",
            "That page or resource was not found.",
        )

    @app.errorhandler(405)
    def method_not_allowed(e):
        return _error_response(
            405,
            "Method not allowed",
            "This action is not allowed for that URL.",
        )

    @app.errorhandler(413)
    def payload_too_large(e):
        return _error_response(
            413,
            "File too large",
            "The uploaded file is too large. Please try a smaller PDF or DOCX.",
        )

    @app.errorhandler(422)
    def unprocessable(e):
        return _error_response(
            422,
            "Unprocessable",
            "We could not process that submission. Please review your input.",
        )

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception("Unhandled server error")
        return _error_response(
            500,
            "Server error",
            "Something went wrong on our side. Your saved profile is safe — please try again.",
        )

def _ensure_upload_folder(app: Flask) -> None:
    upload = app.config.get("UPLOAD_FOLDER")
    if upload is None:
        upload = Path(app.root_path) / "static" / "uploads"
        app.config["UPLOAD_FOLDER"] = upload
    path = Path(upload)
    path.mkdir(parents=True, exist_ok=True)


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"


def _register_user_loader() -> None:
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None


def _register_blueprints(app: Flask) -> None:
    """Register route blueprints when present (foundation-safe)."""
    blueprint_specs = (
        ("app.routes.auth", "bp", None),
        ("app.routes.student", "bp", "/student"),
        ("app.routes.intelligence", "bp", "/student"),
        ("app.routes.admin", "bp", "/admin"),
        ("app.routes.api", "bp", "/api"),
        ("app.routes.main", "bp", None),
    )
    for module_name, attr, url_prefix in blueprint_specs:
        try:
            module = __import__(module_name, fromlist=[attr])
        except ImportError:
            continue
        bp = getattr(module, attr, None)
        if bp is None:
            continue
        if url_prefix:
            app.register_blueprint(bp, url_prefix=url_prefix)
        else:
            app.register_blueprint(bp)
