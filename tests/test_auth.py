"""Integration tests for authentication routes (login, register, logout, profile)."""
import pytest
from tests.conftest import make_user, login


# ---------------------------------------------------------------------------
# GET /login and /register
# ---------------------------------------------------------------------------

class TestAuthPages:
    def test_login_page_loads(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200

    def test_register_page_loads(self, client):
        resp = client.get("/register")
        assert resp.status_code == 200

    def test_login_redirects_authenticated_user(self, client, db):
        make_user(db, email="auth_redir@example.com")
        login(client, email="auth_redir@example.com")
        resp = client.get("/login", follow_redirects=False)
        assert resp.status_code == 302

    def test_register_redirects_authenticated_user(self, client, db):
        make_user(db, email="reg_redir@example.com")
        login(client, email="reg_redir@example.com")
        resp = client.get("/register", follow_redirects=False)
        assert resp.status_code == 302

    def test_forgot_password_page_loads(self, client):
        resp = client.get("/forgot-password")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /logout
# ---------------------------------------------------------------------------

class TestLogout:
    def test_logout_requires_login(self, client):
        resp = client.post("/logout", follow_redirects=False)
        # Should redirect to /login
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_logout_redirects_to_login(self, client, db):
        make_user(db, email="logout_test@example.com")
        login(client, email="logout_test@example.com")
        resp = client.post("/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_logout_get_method_not_allowed(self, client, db):
        make_user(db, email="logout_get@example.com")
        login(client, email="logout_get@example.com")
        # GET request to /logout must be rejected with 405 Method Not Allowed to prevent CSRF logout
        resp = client.get("/logout")
        assert resp.status_code == 405


# ---------------------------------------------------------------------------
# GET /profile
# ---------------------------------------------------------------------------

class TestProfile:
    def test_profile_requires_login(self, client):
        resp = client.get("/profile", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_profile_page_loads_for_logged_in_user(self, client, db):
        make_user(db, email="profile_view@example.com")
        login(client, email="profile_view@example.com")
        resp = client.get("/profile")
        assert resp.status_code == 200

    def test_profile_update_name(self, client, db):
        make_user(db, email="profile_update@example.com")
        login(client, email="profile_update@example.com")
        resp = client.post(
            "/profile",
            data={"name": "New Name", "age": "25", "height": "175", "weight": "70"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        from models import User
        user = User.query.filter_by(email="profile_update@example.com").first()
        assert user.name == "New Name"
        assert user.age == 25
        assert user.height == pytest.approx(175.0)
        assert user.weight == pytest.approx(70.0)

    def test_profile_rejects_invalid_numbers(self, client, db):
        make_user(db, email="profile_bad@example.com")
        login(client, email="profile_bad@example.com")
        resp = client.post(
            "/profile",
            data={"name": "Test", "age": "not_a_number"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # Flash message should mention numbers
        assert b"valid" in resp.data.lower() or b"number" in resp.data.lower()


# ---------------------------------------------------------------------------
# Firebase auth endpoint – minimal smoke test (no real Firebase token)
# ---------------------------------------------------------------------------

class TestFirebaseEndpoint:
    def test_firebase_auth_missing_token(self, client):
        resp = client.post(
            "/api/auth/firebase",
            json={},
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert b"token" in resp.data.lower()
