"""Unit and integration tests for AI coach context layer and safety prompt."""
from datetime import date, timedelta
import pytest
from tests.conftest import make_user, login
from models import FoodLog, GymLog, WorkoutSet, SleepLog, WeightLog, UserPreference, get_or_create_user_preferences
from routes.dashboard import build_coach_context, format_coach_system_prompt

TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
SEVEN_DAYS_AGO = (date.today() - timedelta(days=6)).isoformat()


class TestCoachContextLayer:
    def test_build_coach_context_structure(self, db):
        user = make_user(db, email="coach_struct@example.com")
        user.age = 28
        user.height = 178.0
        user.weight = 75.0
        user.goal_calories = 2200
        user.goal_protein = 160
        db.session.commit()

        pref = get_or_create_user_preferences(user.id)
        pref.fitness_goal = "muscle_gain"
        pref.diet_type = "vegetarian"
        pref.experience_level = "intermediate"
        pref.equipment_access = "full_gym"
        pref.injury_notes = "Right shoulder impingement"
        db.session.commit()

        # Add nutrition logs
        fl = FoodLog(user_id=user.id, date=TODAY, meal="Lunch", food="Paneer Curry", qty=1, calories=260, protein=12, fat=18, sugar=2)
        db.session.add(fl)

        # Add gym workout and sets
        gl = GymLog(user_id=user.id, date=TODAY, muscle="Chest", exercise="Bench Press (Barbell)", sets=3, reps=24, weight=80.0, speed=0, incline=0, intensity="Hard", duration=0, calories=150)
        db.session.add(gl)
        db.session.flush()

        ws = WorkoutSet(gym_log_id=gl.id, set_number=1, reps=8, weight=80.0, completed=True)
        db.session.add(ws)

        # Add weight log
        wl1 = WeightLog(user_id=user.id, date=SEVEN_DAYS_AGO, weight=74.2)
        wl2 = WeightLog(user_id=user.id, date=TODAY, weight=75.0)
        db.session.add_all([wl1, wl2])

        # Add sleep log
        sl = SleepLog(user_id=user.id, date=TODAY, hours=7.5)
        db.session.add(sl)
        db.session.commit()

        ctx = build_coach_context(user.id)

        assert ctx["user_id"] == user.id
        assert ctx["age"] == 28
        assert ctx["height_cm"] == pytest.approx(178.0)
        assert ctx["weight_kg"] == pytest.approx(75.0)
        assert ctx["preferences"]["fitness_goal"] == "muscle_gain"
        assert ctx["preferences"]["diet_type"] == "vegetarian"
        assert ctx["preferences"]["injury_notes"] == "Right shoulder impingement"
        assert ctx["goals"]["calories"] == 2200
        assert ctx["goals"]["protein"] == 160
        assert ctx["goals"]["tdee"] is not None

        # Verify weight delta (+0.8 kg)
        assert ctx["starting_weight_14d"] == pytest.approx(74.2)
        assert ctx["weight_delta_14d"] == pytest.approx(0.8)

        # Verify today's snapshot
        assert ctx["today"]["food_calories"] == pytest.approx(260.0)
        assert ctx["today"]["protein_g"] == pytest.approx(12.0)
        assert ctx["today"]["estimated_gym_calories"] == pytest.approx(150.0)
        assert ctx["today"]["sleep_hours"] == pytest.approx(7.5)

        # Verify top PRs
        assert len(ctx["top_prs"]) >= 1
        assert "Bench Press (Barbell)" in ctx["top_prs"][0]

    def test_user_isolation(self, db):
        user_a = make_user(db, email="user_a_coach@example.com")
        user_b = make_user(db, email="user_b_coach@example.com")

        pref_a = get_or_create_user_preferences(user_a.id)
        pref_a.injury_notes = "Secret injury of user A"
        db.session.commit()

        ctx_b = build_coach_context(user_b.id)
        assert ctx_b["preferences"]["injury_notes"] != "Secret injury of user A"
        assert ctx_b["user_id"] == user_b.id

    def test_format_coach_system_prompt_guardrails(self, db):
        user = make_user(db, email="prompt_guard@example.com")
        pref = get_or_create_user_preferences(user.id)
        pref.diet_type = "vegan"
        pref.equipment_access = "home_bodyweight"
        pref.injury_notes = "Herniated disc L5-S1"
        db.session.commit()

        ctx = build_coach_context(user.id)
        prompt = format_coach_system_prompt(ctx)

        # Safety & Persona Assertions
        assert "VitalLog Coach" in prompt
        assert "Vegan" in prompt
        assert "Home Bodyweight" in prompt
        assert "Herniated disc L5-S1" in prompt
        assert "Non-judgmental" in prompt or "non-judgmental" in prompt
        assert "estimate" in prompt.lower()
        assert "doctor" in prompt.lower()
        assert "cannot and do not alter logs" in prompt

    def test_chat_empty_message_rejected(self, client, db):
        user = make_user(db, email="chat_empty@example.com")
        login(client, email="chat_empty@example.com")

        resp = client.post("/chat", json={"message": "   "})
        assert resp.status_code == 400
        assert "Please enter a message" in resp.get_json()["reply"]
