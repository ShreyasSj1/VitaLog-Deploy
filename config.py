import os
from pathlib import Path

class Config:
    # Environment mode detection
    IS_PRODUCTION = (
        os.environ.get("RENDER") is not None
        or os.environ.get("FLASK_ENV") == "production"
        or os.environ.get("FLASK_DEBUG", "true").lower() == "false"
    )

    _secret = os.environ.get("SECRET_KEY")
    if IS_PRODUCTION and (not _secret or _secret in ("change-me-in-production", "test-secret-key")):
        # Only enforce if not explicitly running automated tests
        if os.environ.get("PYTEST_CURRENT_TEST") is None and not os.environ.get("TESTING"):
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: SECRET_KEY must be set to a secure, "
                "random string in production environments."
            )

    SECRET_KEY = _secret or "dev-insecure-secret-key-for-local-development-only"

    # Session cookie security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = IS_PRODUCTION
    
    # SQLAlchemy Configuration
    default_db_path = Path(__file__).parent / "fitness.db"
    raw_db_url = os.environ.get("DATABASE_URL", f"sqlite:///{default_db_path}")

    # Render/Heroku-style URLs may be "postgres://...".
    # SQLAlchemy 2 defaults to psycopg2 for "postgresql://..." unless a driver is explicit.
    # We install psycopg (v3), so force the URL to use the psycopg driver.
    if raw_db_url.startswith("postgres://"):
        raw_db_url = raw_db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif raw_db_url.startswith("postgresql://"):
        raw_db_url = raw_db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    
    SQLALCHEMY_DATABASE_URI = raw_db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "")
    FIREBASE_AUTH_DOMAIN = os.environ.get("FIREBASE_AUTH_DOMAIN", "")
    FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "")
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
