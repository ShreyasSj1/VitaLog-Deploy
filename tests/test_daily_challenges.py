"""Unit and integration tests for Daily Workout Challenges (WOD)."""
import pytest
from datetime import date
from daily_challenges import get_daily_challenge, is_challenge_completed, DAILY_CHALLENGES
from models import GymLog, User
from tests.conftest import make_user, login

TODAY = date.today().isoformat()


class TestDailyChallenges:
    def test_daily_challenge_catalog_validity(self):
        assert len(DAILY_CHALLENGES) >= 10
        for ch in DAILY_CHALLENGES:
            assert "id" in ch
            assert "title" in ch
            assert "muscle" in ch
            assert "target" in ch
            assert "calories" in ch
            assert ch["calories"] > 0
            assert "duration" in ch
            assert len(ch["instructions"]) >= 2

    def test_get_daily_challenge_deterministic(self):
        c1 = get_daily_challenge("2026-08-29")
        c2 = get_daily_challenge("2026-08-29")
        assert c1["title"] == c2["title"]
        assert c1["id"] == c2["id"]
        assert c1["date"] == "2026-08-29"

        # Different date should return valid challenge
        c3 = get_daily_challenge("2026-08-30")
        assert "title" in c3

    def test_complete_challenge_requires_login(self, client):
        resp = client.post("/gym/complete-challenge", json={"date": TODAY})
        assert resp.status_code == 302

    def test_complete_challenge_success(self, client, db):
        make_user(db, email="wod_user@example.com")
        login(client, email="wod_user@example.com")

        challenge = get_daily_challenge(TODAY)
        resp = client.post(
            "/gym/complete-challenge",
            json={"date": TODAY, "elapsed_seconds": 720}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["already_completed"] is False
        assert data["calories"] == challenge["calories"]

        # Verify GymLog entry created
        user = User.query.filter_by(email="wod_user@example.com").first()
        log = GymLog.query.filter_by(user_id=user.id, date=TODAY).first()
        assert log is not None
        assert f"Daily Challenge: {challenge['title']}" in log.exercise
        assert log.calories == challenge["calories"]

    def test_complete_challenge_idempotent(self, client, db):
        make_user(db, email="wod_user2@example.com")
        login(client, email="wod_user2@example.com")

        # First completion
        resp1 = client.post("/gym/complete-challenge", json={"date": TODAY})
        assert resp1.status_code == 200
        assert resp1.get_json()["already_completed"] is False

        # Second completion should return already_completed True
        resp2 = client.post("/gym/complete-challenge", json={"date": TODAY})
        assert resp2.status_code == 200
        assert resp2.get_json()["already_completed"] is True

    def test_challenge_renders_on_dashboard_and_gym(self, client, db):
        make_user(db, email="wod_view@example.com")
        login(client, email="wod_view@example.com")

        # Test index (home) view
        resp_index = client.get("/")
        assert resp_index.status_code == 200
        html_index = resp_index.data.decode("utf-8")
        assert "DAILY CHALLENGE" in html_index
        assert 'id="dailyChallengeCard"' in html_index

        # Test gym view
        resp_gym = client.get(f"/gym?date={TODAY}")
        assert resp_gym.status_code == 200
        html_gym = resp_gym.data.decode("utf-8")
        assert "DAILY CHALLENGE" in html_gym
        assert 'id="dailyChallengeCard"' in html_gym
