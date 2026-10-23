"""Integration tests for set-by-set workouts and PR detection."""
from datetime import date
import pytest
from tests.conftest import make_user, login
from models import GymLog, WorkoutSet

TODAY = date.today().isoformat()


class TestWorkoutSetsAndPRs:
    def test_save_gym_sets_api(self, client, db):
        user = make_user(db, email="gym_sets@example.com")
        login(client, email="gym_sets@example.com")

        payload = {
            "date": TODAY,
            "muscle": "Chest",
            "exercise": "Bench Press (Barbell)",
            "intensity": "Hard",
            "sets": [
                {"reps": 10, "weight": 60.0, "rpe": 8.0},
                {"reps": 8, "weight": 70.0, "rpe": 8.5},
                {"reps": 6, "weight": 80.0, "rpe": 9.5},
            ],
        }

        resp = client.post("/gym/sets/save", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["gym_log_id"] is not None
        assert data["estimated_1rm"] > 80.0  # 80 * (1 + 6/30) = 96.0

        # Verify DB records
        log = db.session.get(GymLog, data["gym_log_id"])
        assert log is not None
        assert log.sets == 3
        assert log.reps == 24
        assert log.weight == pytest.approx(80.0)

        sets = WorkoutSet.query.filter_by(gym_log_id=log.id).order_by(WorkoutSet.set_number).all()
        assert len(sets) == 3
        assert sets[0].set_number == 1
        assert sets[0].weight == pytest.approx(60.0)
        assert sets[0].reps == 10
        assert sets[0].rpe == pytest.approx(8.0)

        assert sets[2].set_number == 3
        assert sets[2].weight == pytest.approx(80.0)
        assert sets[2].reps == 6

    def test_personal_record_detection(self, client, db):
        user = make_user(db, email="gym_pr@example.com")
        login(client, email="gym_pr@example.com")

        # Session 1: Squats @ 100kg x 5 -> est 1RM = 100 * (1 + 5/30) = 116.67
        resp1 = client.post(
            "/gym/sets/save",
            json={
                "date": "2026-04-10",
                "muscle": "Legs",
                "exercise": "Squats (Barbell)",
                "sets": [{"reps": 5, "weight": 100.0}],
            },
        )
        assert resp1.status_code == 200
        assert resp1.get_json()["is_pr"] is False  # First session, no prior to beat

        # Session 2: Squats @ 105kg x 5 -> est 1RM = 105 * (1 + 5/30) = 122.5 > 116.67 (New PR!)
        resp2 = client.post(
            "/gym/sets/save",
            json={
                "date": "2026-04-17",
                "muscle": "Legs",
                "exercise": "Squats (Barbell)",
                "sets": [{"reps": 5, "weight": 105.0}],
            },
        )
        assert resp2.status_code == 200
        assert resp2.get_json()["is_pr"] is True

        # Session 3: Deload Squats @ 80kg x 8 -> est 1RM = 80 * (1 + 8/30) = 101.3 < 122.5 (No PR)
        resp3 = client.post(
            "/gym/sets/save",
            json={
                "date": "2026-04-24",
                "muscle": "Legs",
                "exercise": "Squats (Barbell)",
                "sets": [{"reps": 8, "weight": 80.0}],
            },
        )
        assert resp3.status_code == 200
        assert resp3.get_json()["is_pr"] is False

    def test_exercise_history_endpoint(self, client, db):
        user = make_user(db, email="gym_history@example.com")
        login(client, email="gym_history@example.com")

        client.post(
            "/gym/sets/save",
            json={
                "date": TODAY,
                "muscle": "Back",
                "exercise": "Deadlift",
                "sets": [
                    {"reps": 5, "weight": 120.0},
                    {"reps": 3, "weight": 140.0},
                ],
            },
        )

        resp = client.get("/api/exercise-history?exercise=Deadlift")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["exercise"] == "Deadlift"
        assert len(data["history"]) == 1
        assert len(data["history"][0]["sets"]) == 2

    def test_legacy_gym_post_backward_compatibility(self, client, db):
        user = make_user(db, email="gym_legacy@example.com")
        login(client, email="gym_legacy@example.com")

        resp = client.post(
            f"/gym?date={TODAY}",
            data={
                "muscle": "Arms",
                "exercise": "Bicep Curls (Dumbbell)",
                "sets": "3",
                "reps": "12",
                "weight": "14",
                "intensity": "Medium",
                "date": TODAY,
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        log = GymLog.query.filter_by(user_id=user.id, exercise="Bicep Curls (Dumbbell)").first()
        assert log is not None
        assert log.sets == 3
        # Should have auto-created 3 WorkoutSet rows
        assert len(log.sets_detail) == 3
        assert log.sets_detail[0].set_number == 1
        assert log.sets_detail[0].weight == pytest.approx(14.0)
        assert log.sets_detail[0].reps == 12
