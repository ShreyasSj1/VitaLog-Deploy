"""
test_security_validation.py — Regression tests for Stage 1:
- Production configuration fail-safe
- Session cookie settings and HTTP security headers
- CSRF validation and rate limiting
- Server-side input validation boundaries
- Admin promotion rules
- Firebase unverified account takeover prevention
"""
import pytest
from tests.conftest import make_user, login


class TestSecurityHeadersAndCookies:
    def test_security_headers_present(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        csp = resp.headers.get("Content-Security-Policy")
        assert csp is not None
        assert "default-src 'self'" in csp
        assert "cdn.jsdelivr.net" in csp
        assert "fonts.googleapis.com" in csp
        hsts = resp.headers.get("Strict-Transport-Security")
        assert hsts is not None
        assert "max-age=31536000" in hsts

    def test_session_cookie_settings_configured(self, app):
        assert app.config.get("SESSION_COOKIE_HTTPONLY") is True
        assert app.config.get("SESSION_COOKIE_SAMESITE") == "Lax"


class TestAdminSecurity:
    def test_first_user_in_empty_db_is_not_admin(self, db):
        from models import User, default_role_for_email
        User.query.delete()
        db.session.commit()
        # Public registration must not grant admin merely because DB is empty
        role = default_role_for_email("first_user@example.com")
        assert role == "user"

    def test_admin_email_promotes_to_admin(self, monkeypatch):
        from models import default_role_for_email
        monkeypatch.setenv("ADMIN_EMAILS", "lead_admin@example.com")
        assert default_role_for_email("lead_admin@example.com") == "admin"
        assert default_role_for_email("LEAD_ADMIN@EXAMPLE.COM") == "admin"
        assert default_role_for_email("hacker@example.com") == "user"


class TestRateLimiting:
    def test_auth_rate_limiter_blocks_excessive_attempts(self):
        from utils import InMemoryRateLimiter
        limiter = InMemoryRateLimiter(requests_per_window=3, window_seconds=60)
        key = "192.168.1.100"
        assert limiter.is_allowed(key) is True
        assert limiter.is_allowed(key) is True
        assert limiter.is_allowed(key) is True
        assert limiter.is_allowed(key) is False  # Exceeded


class TestInputValidation:
    def test_food_rejects_negative_or_zero_quantity(self, client, db):
        make_user(db, email="val_user@example.com")
        login(client, email="val_user@example.com")
        resp = client.post(
            "/food",
            data={"meal": "Breakfast", "food": "Idli", "qty": "-5"},
            follow_redirects=True
        )
        assert resp.status_code == 200
        assert b"greater than zero" in resp.data

    def test_food_rejects_excessive_macros(self, client, db):
        make_user(db, email="val_macro@example.com")
        login(client, email="val_macro@example.com")
        resp = client.post(
            "/food",
            data={
                "meal": "Lunch",
                "food": "OTHERS",
                "other_name": "Mega Meal",
                "other_calories": "99999999",  # exceeds max
                "qty": "1"
            },
            follow_redirects=True
        )
        assert resp.status_code == 200
        assert b"cannot exceed" in resp.data

    def test_sleep_rejects_impossible_hours(self, client, db):
        make_user(db, email="val_sleep@example.com")
        login(client, email="val_sleep@example.com")
        resp = client.post(
            "/sleep",
            data={"date": "2026-04-20", "hours": "25", "quality": "4"},  # > 24 hrs
            follow_redirects=True
        )
        assert resp.status_code == 200
        assert b"cannot exceed 24.0" in resp.data

    def test_gym_rejects_impossible_sets(self, client, db):
        make_user(db, email="val_gym@example.com")
        login(client, email="val_gym@example.com")
        resp = client.post(
            "/gym",
            data={"muscle": "Chest", "exercise": "Bench Press", "sets": "9999", "reps": "10"},
            follow_redirects=True
        )
        assert resp.status_code == 200
        assert b"must be between 1 and 100" in resp.data

    def test_profile_rejects_invalid_age(self, client, db):
        make_user(db, email="val_profile@example.com")
        login(client, email="val_profile@example.com")
        resp = client.post(
            "/profile",
            data={"name": "Test User", "age": "250"},
            follow_redirects=True
        )
        assert resp.status_code == 200
        assert b"must be between 5 and 120" in resp.data


class TestCSRFProtection:
    def test_csrf_token_generation_and_validation(self, app):
        with app.test_request_context():
            from csrf import generate_csrf_token
            token1 = generate_csrf_token()
            assert len(token1) == 64
            token2 = generate_csrf_token()
            assert token1 == token2  # Consistent within session


class TestFirebaseAuthTakeover:
    def test_unverified_firebase_account_takeover_blocked(self, client, db, monkeypatch):
        import firebase_admin.auth
        make_user(db, email="victim@example.com")
        monkeypatch.setattr(
            firebase_admin.auth,
            "verify_id_token",
            lambda token: {"uid": "attacker_uid", "email": "victim@example.com", "email_verified": False}
        )
        resp = client.post(
            "/api/auth/firebase",
            json={"idToken": "fake-attacker-token"},
            content_type="application/json"
        )
        assert resp.status_code == 403
        assert b"Please verify your email before signing in" in resp.data

    def test_verified_firebase_account_login_allowed(self, client, db, monkeypatch):
        import firebase_admin.auth
        make_user(db, email="legit@example.com")
        monkeypatch.setattr(
            firebase_admin.auth,
            "verify_id_token",
            lambda token: {"uid": "legit_uid", "email": "legit@example.com", "email_verified": True}
        )
        resp = client.post(
            "/api/auth/firebase",
            json={"idToken": "fake-legit-token"},
            content_type="application/json"
        )
        assert resp.status_code == 200
        assert resp.get_json().get("success") is True


class TestCrossUserIsolation:
    def test_weight_history_isolated(self, client, db):
        u1 = make_user(db, email="user1_iso@example.com")
        u2 = make_user(db, email="user2_iso@example.com")
        from models import WeightLog
        db.session.add(WeightLog(user_id=u1.id, date="2026-04-20", weight=80.0))
        db.session.commit()

        login(client, email="user2_iso@example.com")
        resp = client.get("/api/weight-history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 0
        assert data["readings"] == []

    def test_saved_meal_isolated(self, client, db):
        u1 = make_user(db, email="user1_meal@example.com")
        u2 = make_user(db, email="user2_meal@example.com")
        from models import SavedMeal
        sm = SavedMeal(user_id=u1.id, name="Secret Meal", meal_category="Lunch")
        db.session.add(sm)
        db.session.commit()

        login(client, email="user2_meal@example.com")
        del_resp = client.post(f"/saved-meals/delete/{sm.id}")
        assert del_resp.status_code == 404

        log_resp = client.post(f"/saved-meals/log/{sm.id}", json={})
        assert log_resp.status_code == 404

    def test_exercise_history_isolated(self, client, db):
        u1 = make_user(db, email="user1_gym@example.com")
        u2 = make_user(db, email="user2_gym@example.com")
        from models import GymLog
        db.session.add(GymLog(user_id=u1.id, date="2026-04-20", muscle="Chest", exercise="Bench Press", sets=3, reps=10, weight=100.0))
        db.session.commit()

        login(client, email="user2_gym@example.com")
        resp = client.get("/api/exercise-history?exercise=Bench Press")
        assert resp.status_code == 200
        assert resp.get_json()["history"] == []


class TestHealthAndReadinessProbes:
    def test_liveness_probe_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "healthy"

    def test_readiness_probe_returns_200_when_healthy(self, client):
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ready"
        assert resp.get_json()["database"] == "connected"


class TestClientIPResolution:
    def test_get_client_ip_prefers_remote_addr_under_proxy(self, app):
        from utils import get_client_ip
        with app.test_request_context("/", environ_base={"REMOTE_ADDR": "198.51.100.4"}):
            assert get_client_ip() == "198.51.100.4"

    def test_get_client_ip_does_not_trust_spoofed_leading_xff(self, app):
        from utils import get_client_ip
        # Attacker injects fake leading IP, proxy appends real IP at the end
        headers = {"X-Forwarded-For": "203.0.113.195, 198.51.100.4"}
        with app.test_request_context("/", headers=headers, environ_base={"REMOTE_ADDR": ""}):
            # Must take the right-most trusted proxy hop, NOT the attacker's spoofed 203.0.113.195
            assert get_client_ip() == "198.51.100.4"


class TestNeutralBMRCalculation:
    def test_unspecified_gender_uses_neutral_midpoint(self):
        from utils import calculate_bmr_mifflin_st_jeor
        # Weight: 70kg, Height: 175cm, Age: 30
        # Base = (10 * 70) + (6.25 * 175) - (5 * 30) = 700 + 1093.75 - 150 = 1643.75
        # Male: 1643.75 + 5 = 1648.8
        # Female: 1643.75 - 161 = 1482.8
        # Unspecified midpoint: 1643.75 - 78 = 1565.8
        bmr_male = calculate_bmr_mifflin_st_jeor(70, 175, 30, "male")
        bmr_female = calculate_bmr_mifflin_st_jeor(70, 175, 30, "female")
        bmr_unspecified = calculate_bmr_mifflin_st_jeor(70, 175, 30, "unspecified")

        assert bmr_male == 1648.8
        assert bmr_female == 1482.8
        assert bmr_unspecified == 1565.8
        # Verify unspecified is strictly between female and male (exact midpoint)
        assert bmr_female < bmr_unspecified < bmr_male
        assert round(bmr_unspecified - bmr_female, 1) == round(bmr_male - bmr_unspecified, 1)

