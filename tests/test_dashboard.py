"""Integration tests for dashboard routes (food, sleep, gym, wellbeing, report)."""
from datetime import date
import pytest
from tests.conftest import make_user, login

TODAY = date.today().isoformat()


# ---------------------------------------------------------------------------
# Main dashboard /
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_index_requires_login(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_index_loads_for_logged_in_user(self, client, db):
        make_user(db, email="dash@example.com")
        login(client, email="dash@example.com")
        resp = client.get("/")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Food log  /food
# ---------------------------------------------------------------------------

class TestFoodRoutes:
    def test_food_page_requires_login(self, client):
        resp = client.get("/food", follow_redirects=False)
        assert resp.status_code == 302

    def test_food_page_loads(self, client, db):
        make_user(db, email="food_view@example.com")
        login(client, email="food_view@example.com")
        resp = client.get(f"/food?date={TODAY}")
        assert resp.status_code == 200

    def test_add_food_entry_known_item(self, client, db):
        make_user(db, email="food_add@example.com")
        login(client, email="food_add@example.com")
        resp = client.post(
            f"/food?date={TODAY}",
            data={"meal": "Breakfast", "food": "Idli", "qty": "2", "date": TODAY},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        from models import FoodLog, User
        user = User.query.filter_by(email="food_add@example.com").first()
        log = FoodLog.query.filter_by(user_id=user.id, date=TODAY).first()
        assert log is not None
        assert log.food == "Idli"
        assert log.qty == pytest.approx(2.0)
        assert log.calories == pytest.approx(90.0)  # 45 * 2

    def test_add_food_entry_custom_item(self, client, db):
        make_user(db, email="food_custom@example.com")
        login(client, email="food_custom@example.com")
        resp = client.post(
            f"/food?date={TODAY}",
            data={
                "meal": "Snacks", "food": "OTHERS",
                "other_name": "My Protein Bar",
                "other_calories": "200",
                "other_protein": "20",
                "other_fat": "5",
                "other_sugar": "3",
                "qty": "1", "date": TODAY,
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        from models import FoodLog, User
        user = User.query.filter_by(email="food_custom@example.com").first()
        log = FoodLog.query.filter_by(user_id=user.id, food="My Protein Bar").first()
        assert log is not None
        assert log.calories == pytest.approx(200.0)

    def test_delete_food_entry(self, client, db):
        make_user(db, email="food_del@example.com")
        login(client, email="food_del@example.com")
        # Add entry first
        client.post(
            f"/food?date={TODAY}",
            data={"meal": "Breakfast", "food": "Omelette", "qty": "1", "date": TODAY},
        )
        from models import FoodLog, User
        user = User.query.filter_by(email="food_del@example.com").first()
        log = FoodLog.query.filter_by(user_id=user.id).first()
        assert log is not None
        # Delete it
        resp = client.post(
            f"/food/delete/{log.id}",
            data={"date": TODAY},
            follow_redirects=True,
        )
        deleted = db.session.get(FoodLog, log.id)
        assert deleted is None

    def test_add_food_invalid_qty(self, client, db):
        make_user(db, email="food_badqty@example.com")
        login(client, email="food_badqty@example.com")
        resp = client.post(
            f"/food?date={TODAY}",
            data={"meal": "Breakfast", "food": "Idli", "qty": "-1", "date": TODAY},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # Should flash a validation error, not create a log
        from models import FoodLog, User
        user = User.query.filter_by(email="food_badqty@example.com").first()
        count = FoodLog.query.filter_by(user_id=user.id).count()
        assert count == 0


# ---------------------------------------------------------------------------
# Sleep log  /sleep
# ---------------------------------------------------------------------------

class TestSleepRoutes:
    def test_sleep_page_loads(self, client, db):
        make_user(db, email="sleep_view@example.com")
        login(client, email="sleep_view@example.com")
        resp = client.get(f"/sleep?date={TODAY}")
        assert resp.status_code == 200

    def test_add_sleep_entry(self, client, db):
        make_user(db, email="sleep_add@example.com")
        login(client, email="sleep_add@example.com")
        resp = client.post(
            "/sleep",
            data={"date": TODAY, "hours": "7.5", "quality": "4", "notes": "Good rest"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        from models import SleepLog, User
        user = User.query.filter_by(email="sleep_add@example.com").first()
        log = SleepLog.query.filter_by(user_id=user.id, date=TODAY).first()
        assert log is not None
        assert log.hours == pytest.approx(7.5)
        assert log.quality == 4

    def test_update_sleep_upserts(self, client, db):
        """Posting sleep for the same date should update, not duplicate."""
        make_user(db, email="sleep_upsert@example.com")
        login(client, email="sleep_upsert@example.com")
        client.post("/sleep", data={"date": TODAY, "hours": "6", "quality": "3"})
        client.post("/sleep", data={"date": TODAY, "hours": "8", "quality": "5"})
        from models import SleepLog, User
        user = User.query.filter_by(email="sleep_upsert@example.com").first()
        logs = SleepLog.query.filter_by(user_id=user.id, date=TODAY).all()
        assert len(logs) == 1
        assert logs[0].hours == pytest.approx(8.0)

    def test_delete_sleep_entry(self, client, db):
        make_user(db, email="sleep_del@example.com")
        login(client, email="sleep_del@example.com")
        client.post("/sleep", data={"date": TODAY, "hours": "7", "quality": "3"})
        resp = client.post(
            "/sleep/delete",
            data={"date": TODAY},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        from models import SleepLog, User
        user = User.query.filter_by(email="sleep_del@example.com").first()
        log = SleepLog.query.filter_by(user_id=user.id, date=TODAY).first()
        assert log is None


# ---------------------------------------------------------------------------
# Wellbeing log  /wellbeing
# ---------------------------------------------------------------------------

class TestWellbeingRoutes:
    def test_wellbeing_page_loads(self, client, db):
        make_user(db, email="wb_view@example.com")
        login(client, email="wb_view@example.com")
        resp = client.get(f"/wellbeing?date={TODAY}")
        assert resp.status_code == 200

    def test_add_wellbeing_entry(self, client, db):
        make_user(db, email="wb_add@example.com")
        login(client, email="wb_add@example.com")
        resp = client.post(
            "/wellbeing",
            data={"activity": "Yoga", "minutes": "30", "date": TODAY},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        from models import WellbeingLog, User
        user = User.query.filter_by(email="wb_add@example.com").first()
        log = WellbeingLog.query.filter_by(user_id=user.id, date=TODAY).first()
        assert log is not None
        assert log.activity == "Yoga"
        assert log.minutes == 30

    def test_add_wellbeing_custom_activity(self, client, db):
        make_user(db, email="wb_custom@example.com")
        login(client, email="wb_custom@example.com")
        resp = client.post(
            "/wellbeing",
            data={"activity": "OTHERS", "other_activity": "Hiking", "minutes": "60", "date": TODAY},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        from models import WellbeingLog, User
        user = User.query.filter_by(email="wb_custom@example.com").first()
        log = WellbeingLog.query.filter_by(user_id=user.id, activity="Hiking").first()
        assert log is not None


# ---------------------------------------------------------------------------
# Gym log  /gym
# ---------------------------------------------------------------------------

class TestGymRoutes:
    def test_gym_page_loads(self, client, db):
        make_user(db, email="gym_view@example.com")
        login(client, email="gym_view@example.com")
        resp = client.get(f"/gym?date={TODAY}")
        assert resp.status_code == 200

    def test_add_strength_exercise(self, client, db):
        make_user(db, email="gym_strength@example.com")
        login(client, email="gym_strength@example.com")
        resp = client.post(
            "/gym",
            data={
                "date": TODAY, "muscle": "Chest", "exercise": "Bench Press",
                "sets": "4", "reps": "10", "weight": "60",
                "intensity": "Medium",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        from models import GymLog, User
        user = User.query.filter_by(email="gym_strength@example.com").first()
        log = GymLog.query.filter_by(user_id=user.id, date=TODAY).first()
        assert log is not None
        assert log.exercise == "Bench Press"
        assert log.calories > 0

    def test_add_cardio_exercise(self, client, db):
        make_user(db, email="gym_cardio@example.com")
        login(client, email="gym_cardio@example.com")
        resp = client.post(
            "/gym",
            data={
                "date": TODAY, "muscle": "Cardio", "exercise": "Treadmill (Running)",
                "duration": "30", "speed": "9", "incline": "0",
                "intensity": "Hard",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        from models import GymLog, User
        user = User.query.filter_by(email="gym_cardio@example.com").first()
        log = GymLog.query.filter_by(user_id=user.id, date=TODAY).first()
        assert log is not None
        assert log.calories > 0
        assert log.sets == 0  # Cardio zeroes out sets/reps/weight

    def test_delete_gym_entry(self, client, db):
        make_user(db, email="gym_del@example.com")
        login(client, email="gym_del@example.com")
        client.post(
            "/gym",
            data={
                "date": TODAY, "muscle": "Arms", "exercise": "Bicep Curl",
                "sets": "3", "reps": "12", "weight": "15", "intensity": "Medium",
            },
        )
        from models import GymLog, User
        user = User.query.filter_by(email="gym_del@example.com").first()
        log = GymLog.query.filter_by(user_id=user.id).first()
        resp = client.post(
            f"/gym/delete/{log.id}",
            data={"date": TODAY},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert db.session.get(GymLog, log.id) is None


# ---------------------------------------------------------------------------
# Report  /report
# ---------------------------------------------------------------------------

class TestReportRoute:
    def test_report_page_loads(self, client, db):
        make_user(db, email="report_view@example.com")
        login(client, email="report_view@example.com")
        resp = client.get(f"/report?date={TODAY}")
        assert resp.status_code == 200

    def test_report_requires_login(self, client):
        resp = client.get("/report", follow_redirects=False)
        assert resp.status_code == 302


class TestDailyHabitScoringAndEnergyBalance:
    def test_habit_score_none_when_unlogged(self, client, db):
        user = make_user(db, email="habit_unlogged@example.com")
        login(client, email="habit_unlogged@example.com")
        resp = client.get(f"/?date={TODAY}")
        assert resp.status_code == 200
        # When unlogged, score should display "--" instead of a false "0%"
        assert b"--" in resp.data
        assert b"No food logged yet today" in resp.data

    def test_habit_score_not_penalized_on_rest_days(self, client, db):
        user = make_user(db, email="habit_rest@example.com")
        login(client, email="habit_rest@example.com")
        # Log food on target (1.0) and healthy sleep (1.0)
        client.post("/food", data={"meal": "Lunch", "food": "Rice", "qty": "1"})
        client.post("/sleep", data={"date": TODAY, "hours": "8.0", "quality": "5"})
        # No gym logged -> rest day
        resp = client.get(f"/?date={TODAY}")
        assert resp.status_code == 200
        # Denominator should only evaluate active logged habits (food + sleep = 2)
        # So score is 100% (2/2), NOT penalized down to 50% for resting
        assert b"Rest / Recovery day" in resp.data
        assert b"100%" in resp.data
