import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _normalize_database_url(url: str) -> str:
    """Render/Heroku sometimes provide postgres:// — SQLAlchemy needs postgresql://."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "edunova-dev-change-me-in-production")
    SQLALCHEMY_DATABASE_URI = _normalize_database_url(
        os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'nexora.db'}")
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
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB
    UPLOAD_FOLDER = BASE_DIR / "app" / "static" / "uploads"
    ALLOWED_RESUME_EXTENSIONS = {"pdf", "docx"}
    DEMO_MODE = os.environ.get("DEMO_MODE", "true").lower() in {"1", "true", "yes"}
    AI_PROVIDER = os.environ.get("AI_PROVIDER", "local")  # local | gemini | openai
    AI_API_KEY = os.environ.get("AI_API_KEY", "")
    AI_MODEL = os.environ.get("AI_MODEL", "")
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
