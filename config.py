import os
from pathlib import Path

# Load .env before Config reads os.environ (local development).
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent


def _normalize_database_url(url: str) -> str:
    """Render/Heroku sometimes provide postgres:// — SQLAlchemy needs postgresql://."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    # Relative sqlite paths are resolved against BASE_DIR so restarts / cwd changes
    # do not create a second empty database (common cause of "lost" accounts).
    if url.startswith("sqlite:///"):
        rest = url[len("sqlite:///") :]
        if rest in {":memory:", ""}:
            return url
        path = Path(rest)
        if not path.is_absolute():
            path = (BASE_DIR / path).resolve()
            return f"sqlite:///{path}"
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "edunova-dev-change-me-in-production")
    SQLALCHEMY_DATABASE_URI = _normalize_database_url(
        os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'edunova.db'}")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_DURATION_DAYS = int(os.environ.get("REMEMBER_COOKIE_DAYS", "14"))
    PERMANENT_SESSION_LIFETIME = int(
        os.environ.get("PERMANENT_SESSION_SECONDS", str(60 * 60 * 24 * 14))
    )
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB
    UPLOAD_FOLDER = BASE_DIR / "app" / "static" / "uploads"
    ALLOWED_RESUME_EXTENSIONS = {"pdf", "docx"}
    DEMO_MODE = os.environ.get("DEMO_MODE", "true").lower() in {"1", "true", "yes"}
    # DEMO_MODE only affects seeding/UX — it does NOT force local AI.
    AI_PROVIDER = os.environ.get("AI_PROVIDER", "local")  # local | gemini | openai | groq
    AI_API_KEY = os.environ.get("AI_API_KEY", "")
    AI_MODEL = os.environ.get("AI_MODEL", "")
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "")
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
    ML_MODEL_PATH = BASE_DIR / "ml" / "models" / "placement_model.joblib"
    ML_META_PATH = BASE_DIR / "ml" / "models" / "placement_meta.json"
    RATE_LIMIT_LOGIN = 20  # soft limit per session window
    DEBUG = os.environ.get("FLASK_DEBUG", os.environ.get("FLASK_ENV", "")).lower() in {
        "1",
        "true",
        "yes",
        "development",
    }


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    DEMO_MODE = True
    DEBUG = False
    AI_PROVIDER = "local"
