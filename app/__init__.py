"""EDUNOVA AI Flask application factory (legacy package path Nexora_AI)."""

from pathlib import Path

from flask import Flask

from app.extensions import csrf, db, login_manager
from config import Config


def create_app(config_object=None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        instance_relative_config=False,
        static_folder="static",
        template_folder="templates",
    )
    app.config.from_object(config_object or Config)

    _ensure_upload_folder(app)
    _init_extensions(app)
    _register_blueprints(app)
    _register_user_loader()

    # Import models so metadata is registered, then create tables.
    # Use importlib so we do not shadow the local Flask `app` variable.
    import importlib

    importlib.import_module("app.models")

    with app.app_context():
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
    @app.errorhandler(403)
    def forbidden(e):
        from flask import render_template

        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template

        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template

        return render_template("errors/500.html"), 500


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
