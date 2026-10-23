"""
Pytest configuration and shared fixtures for VitalLog tests.

Uses an in-memory SQLite database so tests never touch the real fitness.db
and run fully isolated from each other.
"""
import os
import pytest

# Point to in-memory SQLite BEFORE importing the app so config picks it up
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
# Disable Firebase for tests
os.environ.setdefault("FIREBASE_CREDENTIALS_BASE64", "")
# Disable external Groq API calls in test runner so tests run hermetically offline
os.environ["GROQ_API_KEY"] = ""

import firebase_admin  # noqa: E402


def _ensure_no_firebase():
    """Prevent firebase_admin.initialize_app from failing during tests."""
    try:
        firebase_admin.get_app()
    except ValueError:
        # Not yet initialized – mock-initialize with no-op credentials
        try:
            firebase_admin.initialize_app()
        except Exception:
            pass


_ensure_no_firebase()

from app import app as flask_app  # noqa: E402
from extensions import db as _db  # noqa: E402
from models import seed_lookup_tables  # noqa: E402


# ---------------------------------------------------------------------------
# App / DB fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def app():
    """Return the Flask application configured for testing."""
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SERVER_NAME="localhost",
    )
    with flask_app.app_context():
        _db.create_all()
        seed_lookup_tables()
        yield flask_app
        _db.drop_all()


@pytest.fixture()
def client(app):
    """A test client for the Flask application."""
    return app.test_client()


@pytest.fixture()
def db(app):
    """Return the SQLAlchemy db instance inside an active app context."""
    with app.app_context():
        yield _db


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def make_user(db_session, email="test@example.com", name="Test User",
              password="Password123!", role="user"):
    """Create and persist a User for use in tests."""
    from werkzeug.security import generate_password_hash
    from models import User

    user = User(
        email=email,
        name=name,
        password_hash=generate_password_hash(password),
        role=role,
        is_active=1,
    )
    db_session.session.add(user)
    db_session.session.commit()
    return user


def login(client, email="test@example.com", password="Password123!"):
    """Helper that logs a user in via the Firebase endpoint mock."""
    # Since we cannot call real Firebase in tests, we directly set the session
    # using Flask-Login's test helpers.
    from flask_login import login_user
    from models import User
    user = User.query.filter_by(email=email).first()
    if user is None:
        return None
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user
