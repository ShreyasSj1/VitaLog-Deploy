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

    def test_weight_history_days_filtering(self, client, db):
        user = make_user(db, email="weight_filter@example.com")
        login(client, email="weight_filter@example.com")

        old_date = (date.today() - timedelta(days=60)).isoformat()
        recent_date = (date.today() - timedelta(days=5)).isoformat()
        client.post("/weight", data={"date": old_date, "weight": "80.0"})
        client.post("/weight", data={"date": recent_date, "weight": "75.0"})

        # Query with days=30 should only return the recent reading
        resp = client.get("/api/weight-history?days=30")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 1
        assert data["readings"][0]["date"] == recent_date
        assert data["readings"][0]["weight"] == 75.0

    def test_sparse_calendar_rolling_average(self, client, db):
        user = make_user(db, email="weight_sparse@example.com")
        WeightLog.query.filter_by(user_id=user.id).delete()
        db.session.commit()
        login(client, email="weight_sparse@example.com")

        # Two readings 30 days apart
        date1 = (date.today() - timedelta(days=40)).isoformat()
        date2 = (date.today() - timedelta(days=10)).isoformat()
        client.post("/weight", data={"date": date1, "weight": "85.0"})
        client.post("/weight", data={"date": date2, "weight": "75.0"})

        resp = client.get("/api/weight-history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 2
        # Under true 7-calendar-day average, date2 (75.0) must NOT average with date1 (85.0)
        # because date1 is 30 days outside date2's 7-day calendar window [date2 - 6, date2]
        assert data["moving_average"][0] == 85.0
        assert data["moving_average"][1] == 75.0
