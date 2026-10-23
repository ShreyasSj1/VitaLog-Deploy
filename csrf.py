"""
csrf.py — Session-based CSRF protection for VitalLog.

Provides cryptographic double-submit/session token validation for all state-changing
HTTP requests (POST, PUT, DELETE, PATCH).

Exemptions:
- Requests to /api/auth/firebase (authenticated via Google/Firebase signed bearer token)
- When TESTING=True or CSRF_ENABLED=False (in automated tests)
"""
import secrets
from flask import session, request, abort, current_app


class CallableToken(str):
    """String token that is also callable without arguments for Jinja template compatibility."""
    def __call__(self):
        return str(self)


def generate_csrf_token():
    """Return the active CSRF token for this session, generating one if not set."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return CallableToken(session["_csrf_token"])


def validate_csrf():
    """Verify that state-changing requests carry a valid matching CSRF token."""
    # Only validate state-changing methods
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return

    # Check if disabled in configuration or testing
    if not current_app.config.get("CSRF_ENABLED", True):
        return
    if current_app.config.get("TESTING") and not current_app.config.get("FORCE_CSRF_TESTING"):
        return
    if current_app.config.get("WTF_CSRF_ENABLED") is False:
        return

    # Public bearer-token endpoints are exempt from cookie CSRF
    exempt_paths = {"/api/auth/firebase"}
    if request.path in exempt_paths:
        return

    json_data = request.get_json(silent=True) if request.is_json else None
    json_token = json_data.get("csrf_token") if isinstance(json_data, dict) else None
    token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or request.headers.get("X-CSRFToken") or json_token
    expected = session.get("_csrf_token")

    if not token or not expected or not secrets.compare_digest(str(token), str(expected)):
        abort(400, description="CSRF token missing or invalid. Please refresh the page and try again.")
