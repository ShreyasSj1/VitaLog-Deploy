"""Integration tests for dated body-weight tracking."""
from datetime import date, timedelta
import pytest
from tests.conftest import make_user, login
from models import WeightLog, User

TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


class TestWeightLogging:
    def test_weight_requires_login(self, client):
        resp = client.get("/weight", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_weight_page_loads(self, client, db):
        make_user(db, email="weight_page@example.com")
        login(client, email="weight_page@example.com")
        resp = client.get("/weight")
        assert resp.status_code == 200
        assert b"Body Weight Tracker" in resp.data

    def test_log_valid_weight(self, client, db):
        user = make_user(db, email="weight_log@example.com")
        login(client, email="weight_log@example.com")

        resp = client.post(
            "/weight",
            data={"date": TODAY, "weight": "74.5", "notes": "Morning weigh-in"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Weight entry saved" in resp.data

        entry = WeightLog.query.filter_by(user_id=user.id, date=TODAY).first()
        assert entry is not None
        assert entry.weight == pytest.approx(74.5)
        assert entry.notes == "Morning weigh-in"

        # Verify profile weight auto-synced
        refreshed_user = db.session.get(User, user.id)
        assert refreshed_user.weight == pytest.approx(74.5)

    def test_log_weight_validation_error(self, client, db):
        make_user(db, email="weight_err@example.com")
        login(client, email="weight_err@example.com")

        # Invalid zero or negative weight
        resp = client.post(
            "/weight",
            data={"date": TODAY, "weight": "-5", "notes": ""},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"must be greater than zero" in resp.data

        # Invalid non-numeric weight
        resp = client.post(
            "/weight",
            data={"date": TODAY, "weight": "heavy", "notes": ""},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Weight must be a valid number" in resp.data

    def test_weight_history_api(self, client, db):
        user = make_user(db, email="weight_api@example.com")
        login(client, email="weight_api@example.com")

        # Add 3 days of weigh-ins
        dates = [(date.today() - timedelta(days=i)).isoformat() for i in range(3, -1, -1)]
        weights = [76.0, 75.8, 75.5, 75.2]
        for d, w in zip(dates, weights):
            client.post("/weight", data={"date": d, "weight": str(w)})

        resp = client.get("/api/weight-history?days=30")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 4
        assert len(data["readings"]) == 4
        assert data["readings"][-1]["weight"] == pytest.approx(75.2)
        assert len(data["moving_average"]) == 4

    def test_delete_weight_entry(self, client, db):
        user = make_user(db, email="weight_del@example.com")
        login(client, email="weight_del@example.com")

        client.post("/weight", data={"date": YESTERDAY, "weight": "75.0"})
        client.post("/weight", data={"date": TODAY, "weight": "74.8"})

        entry = WeightLog.query.filter_by(user_id=user.id, date=TODAY).first()
        resp = client.post(f"/weight/delete/{entry.id}", follow_redirects=True)
        assert resp.status_code == 200

        assert db.session.get(WeightLog, entry.id) is None
        # Profile weight should roll back to yesterday's 75.0
        refreshed_user = db.session.get(User, user.id)
        assert refreshed_user.weight == pytest.approx(75.0)
