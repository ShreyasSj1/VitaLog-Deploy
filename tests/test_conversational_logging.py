"""
tests/test_conversational_logging.py — Comprehensive tests for conversational food & workout logging.
"""
import os
import json
from datetime import datetime, timedelta
import pytest

from models import (
    User, FoodLog, GymLog, WorkoutSet, PendingLogDraft, FoodItem, Exercise,
    utc_iso, now_utc
)
from conversational_logging import (
    process_conversational_message, confirm_draft, cancel_draft, edit_draft,
    match_food_item, match_exercise, infer_meal_category,
    parse_food_rule_based, parse_workout_rule_based,
    is_valid_food_name, is_confirmation_command, is_cancellation_command
)
from tests.conftest import make_user, login


@pytest.fixture()
def user_a(db):
    u = User.query.filter_by(email="conv_user_a@example.com").first()
    if not u:
        u = make_user(db, email="conv_user_a@example.com", name="Conv User A")
    return u


@pytest.fixture()
def user_b(db):
    u = User.query.filter_by(email="conv_user_b@example.com").first()
    if not u:
        u = make_user(db, email="conv_user_b@example.com", name="Conv User B")
    return u


@pytest.fixture()
def auth_client_a(client, user_a):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_a.id)
        sess["_fresh"] = True
    return client


# ===========================================================================
# 1. Matching, Aliases & Parsing Unit Tests
# ===========================================================================

class TestFoodMatchingAndParsing:
    def test_catalog_food_match(self, app):
        with app.app_context():
            matched = match_food_item("masala dosa")
            assert matched is not None
            assert "Dosa" in matched["name"]
            assert matched["calories"] > 0

    def test_food_alias_resolution(self, app):
        with app.app_context():
            # chapati -> Chapati
            m1 = match_food_item("chapati")
            assert m1 is not None
            assert m1["name"] == "Chapati"

            # pb -> Peanut Butter Sandwich
            m2 = match_food_item("pb")
            assert m2 is not None
            assert "Peanut Butter" in m2["name"]

            # egg -> Boiled Eggs
            m3 = match_food_item("egg")
            assert m3 is not None
            assert "Egg" in m3["name"]

    def test_parse_single_food_with_quantity(self, app):
        with app.app_context():
            res = parse_food_rule_based("I had 2 rotis for lunch")
            assert res["intent"] == "food_log"
            assert res["meal_category"] == "Lunch"
            assert len(res["items"]) >= 1
            roti = res["items"][0]
            assert roti["food"] == "Chapati"
            assert roti["qty"] == 2.0
            assert roti["provenance"] == "catalog"
            assert len(res["missing_fields"]) == 0

    def test_parse_multi_item_meal(self, app):
        with app.app_context():
            res = parse_food_rule_based("For breakfast I had 2 dosas and 1 cup of coffee")
            assert res["intent"] == "food_log"
            assert res["meal_category"] == "Breakfast"
            assert len(res["items"]) == 2
            foods = [it["food"] for it in res["items"]]
            assert any("Dosa" in f for f in foods)
            assert any("Coffee" in f for f in foods)
            assert res["totals"]["calories"] > 0
            assert len(res["missing_fields"]) == 0

    def test_missing_portion_detection(self, app):
        with app.app_context():
            res = parse_food_rule_based("I ate rice")
            assert res["intent"] == "food_log"
            assert len(res["items"]) >= 1
            # Since quantity was not specified, missing_fields should note it
            assert any("portion" in mf or "quantity" in mf for mf in res["missing_fields"])

    def test_unrecognized_food_estimate(self, app):
        with app.app_context():
            res = parse_food_rule_based("I had 1 bowl of grandma homemade stew for dinner")
            assert res["intent"] == "food_log"
            assert res["meal_category"] == "Dinner"
            assert len(res["items"]) == 1
            item = res["items"][0]
            assert item["provenance"] == "ai_estimate"
            assert item["is_estimate"] is True
            assert item["calories"] > 0


class TestWorkoutMatchingAndParsing:
    def test_exercise_alias_resolution(self, app):
        with app.app_context():
            m1 = match_exercise("bench")
            assert m1["name"] == "Bench Press"
            assert m1["muscle"] == "Chest"

            m2 = match_exercise("pushups")
            assert m2["name"] == "Push-Ups"

            m3 = match_exercise("treadmill")
            assert "Treadmill" in m3["name"]

    def test_parse_strength_workout_sets_reps_weight(self, app):
        with app.app_context():
            res = parse_workout_rule_based("Bench press 3 sets of 10 reps at 60kg")
            assert res["intent"] == "workout_log"
            assert len(res["exercises"]) == 1
            ex = res["exercises"][0]
            assert ex["exercise"] == "Bench Press"
            assert ex["sets"] == 3
            assert ex["reps"] == 30
            assert ex["weight"] == 60.0
            assert ex["calories"] > 0
            assert len(ex["sets_detail"]) == 3
            assert ex["sets_detail"][0]["set_number"] == 1
            assert ex["sets_detail"][0]["reps"] == 10
            assert ex["sets_detail"][0]["weight"] == 60.0

    def test_parse_multi_exercise_strength_workout(self, app):
        with app.app_context():
            res = parse_workout_rule_based("Squat 4 sets of 8 at 100kg and bench press 3 sets of 10 at 70kg")
            assert res["intent"] == "workout_log"
            assert len(res["exercises"]) == 2
            names = [e["exercise"] for e in res["exercises"]]
            assert "Squat" in names
            assert "Bench Press" in names

    def test_parse_bodyweight_exercise(self, app):
        with app.app_context():
            res = parse_workout_rule_based("Push-ups 3 sets of 15 reps")
            assert res["intent"] == "workout_log"
            assert len(res["exercises"]) == 1
            ex = res["exercises"][0]
            assert ex["exercise"] == "Push-Ups"
            assert ex["sets"] == 3
            assert ex["weight"] == 0.0
            assert ex["calories"] > 0

    def test_parse_cardio_duration_and_speed(self, app):
        with app.app_context():
            res = parse_workout_rule_based("Running 30 mins at 10 km/h")
            assert res["intent"] == "workout_log"
            assert len(res["exercises"]) == 1
            ex = res["exercises"][0]
            assert ex["is_cardio"] is True
            assert ex["duration"] == 30.0
            assert ex["speed"] == 10.0
            assert ex["calories"] > 0

    def test_parse_cardio_with_incline(self, app):
        with app.app_context():
            res = parse_workout_rule_based("Inclined walking 20 mins at 5 km/h with incline 6")
            assert res["intent"] == "workout_log"
            assert len(res["exercises"]) == 1
            ex = res["exercises"][0]
            assert ex["is_cardio"] is True
            assert ex["duration"] == 20.0
            assert ex["speed"] == 5.0
            assert ex["incline"] == 6.0
            assert ex["calories"] > 0

    def test_incomplete_workout_clarification(self, app):
        with app.app_context():
            res = parse_workout_rule_based("I had a chest workout today")
            assert res["intent"] == "workout_log"
            assert len(res["exercises"]) == 0
            assert len(res["missing_fields"]) > 0


# ===========================================================================
# 2. State Machine & Controller Tests
# ===========================================================================

class TestConversationalLoggingStateMachine:
    def test_food_draft_creation_and_confirmation(self, app, user_a, db):
        with app.app_context():
            FoodLog.query.filter_by(user_id=user_a.id).delete()
            PendingLogDraft.query.filter_by(user_id=user_a.id).delete()
            db.session.commit()

            # 1. User says what they ate
            res1 = process_conversational_message(user_a.id, "I had 2 rotis and a bowl of dal for lunch")
            assert res1["draft"] is not None
            assert res1["draft"]["log_type"] == "food"
            assert res1["draft"]["state"] == "awaiting_confirmation"
            draft_id = res1["draft"]["draft_id"]

            # Verify no food_log records saved yet before confirmation
            fl_count = FoodLog.query.filter_by(user_id=user_a.id).count()
            assert fl_count == 0

            # 2. User confirms via natural language: "looks good, save it"
            res2 = process_conversational_message(user_a.id, "looks good, save it")
            assert res2["success"] is True
            assert res2["draft"]["state"] == "confirmed"

            # Verify database rows were inserted
            logs = FoodLog.query.filter_by(user_id=user_a.id).all()
            assert len(logs) >= 2
            foods = [l.food for l in logs]
            assert "Chapati" in foods
            assert any("Dal" in f for f in foods)
            # Check provenance tracking
            for l in logs:
                assert l.provenance in ["catalog", "ai_estimate"]

    def test_workout_draft_creation_and_confirmation(self, app, user_a, db):
        with app.app_context():
            GymLog.query.filter_by(user_id=user_a.id).delete()
            PendingLogDraft.query.filter_by(user_id=user_a.id).delete()
            db.session.commit()

            # 1. User states workout
            res1 = process_conversational_message(user_a.id, "Bench press 3 sets of 10 at 60kg")
            assert res1["draft"] is not None
            assert res1["draft"]["log_type"] == "workout"
            assert res1["draft"]["state"] == "awaiting_confirmation"

            # 2. Confirm
            res2 = confirm_draft(res1["draft"]["draft_id"], user_a.id)
            assert res2["success"] is True

            # Verify GymLog and WorkoutSet persisted
            gym = GymLog.query.filter_by(user_id=user_a.id, exercise="Bench Press").first()
            assert gym is not None
            assert gym.sets == 3
            assert gym.reps == 30
            assert gym.weight == 60.0
            assert gym.calories > 0

            sets = WorkoutSet.query.filter_by(gym_log_id=gym.id).all()
            assert len(sets) == 3
            for s in sets:
                assert s.reps == 10
                assert s.weight == 60.0
                assert s.completed is True

    def test_idempotent_confirmation(self, app, user_a, db):
        with app.app_context():
            FoodLog.query.filter_by(user_id=user_a.id).delete()
            PendingLogDraft.query.filter_by(user_id=user_a.id).delete()
            db.session.commit()

            res1 = process_conversational_message(user_a.id, "I had 2 rotis for dinner")
            draft_id = res1["draft"]["draft_id"]

            # First confirmation
            res2 = confirm_draft(draft_id, user_a.id)
            assert res2["success"] is True
            initial_count = FoodLog.query.filter_by(user_id=user_a.id).count()

            # Second confirmation (should be idempotent)
            res3 = confirm_draft(draft_id, user_a.id)
            assert res3["success"] is True
            assert res3.get("already_confirmed") is True
            after_count = FoodLog.query.filter_by(user_id=user_a.id).count()
            assert after_count == initial_count

    def test_draft_cancellation(self, app, user_a, db):
        with app.app_context():
            FoodLog.query.filter_by(user_id=user_a.id).delete()
            PendingLogDraft.query.filter_by(user_id=user_a.id).delete()
            db.session.commit()

            res1 = process_conversational_message(user_a.id, "I had 2 rotis for lunch")
            draft_id = res1["draft"]["draft_id"]

            # Cancel draft via conversational command
            res2 = process_conversational_message(user_a.id, "cancel that")
            assert res2["success"] is True
            assert res2["draft"]["state"] == "cancelled"

            # Check database: no rows inserted
            count = FoodLog.query.filter_by(user_id=user_a.id).count()
            assert count == 0

    def test_draft_expiry_enforcement(self, app, user_a, db):
        with app.app_context():
            PendingLogDraft.query.filter_by(user_id=user_a.id).delete()
            db.session.commit()

            res1 = process_conversational_message(user_a.id, "I had 2 rotis for lunch")
            draft_id = res1["draft"]["draft_id"]

            # Artificially age the draft past TTL (30 minutes)
            draft = PendingLogDraft.query.filter_by(draft_id=draft_id).first()
            draft.expires_at = utc_iso(now_utc() - timedelta(minutes=5))
            db.session.commit()

            # Attempt confirmation
            res2 = confirm_draft(draft_id, user_a.id)
            assert res2["success"] is False
            assert "expired" in res2["error"].lower()
            assert res2["code"] == 410

    def test_edit_draft_before_confirmation(self, app, user_a, db):
        with app.app_context():
            FoodLog.query.filter_by(user_id=user_a.id).delete()
            PendingLogDraft.query.filter_by(user_id=user_a.id).delete()
            db.session.commit()

            res1 = process_conversational_message(user_a.id, "I had 1 roti for lunch")
            draft_id = res1["draft"]["draft_id"]

            # User edits draft to 3 rotis
            updates = {
                "meal": "Dinner",
                "items": [
                    {
                        "food": "Chapati",
                        "meal_category": "Dinner",
                        "qty": 3.0,
                        "calories": 270.0,
                        "protein": 9.0,
                        "fat": 9.0,
                        "sugar": 0.0,
                        "provenance": "catalog",
                        "is_estimate": False,
                    }
                ]
            }
            res_edit = edit_draft(draft_id, user_a.id, updates)
            assert res_edit["success"] is True
            assert res_edit["draft"]["data"]["meal"] == "Dinner"
            assert res_edit["draft"]["data"]["totals"]["calories"] == 270.0

            # Confirm edited draft
            res_conf = confirm_draft(draft_id, user_a.id)
            assert res_conf["success"] is True
            saved = FoodLog.query.filter_by(user_id=user_a.id).order_by(FoodLog.id.desc()).first()
            assert saved.food == "Chapati"
            assert saved.qty == 3.0
            assert saved.meal == "Dinner"
            assert saved.calories == 270.0


# ===========================================================================
# 3. HTTP Endpoints & Security Tests
# ===========================================================================

class TestConversationalLoggingEndpoints:
    def test_chat_food_logging_roundtrip(self, auth_client_a, user_a, db):
        with auth_client_a.application.app_context():
            FoodLog.query.filter_by(user_id=user_a.id).delete()
            PendingLogDraft.query.filter_by(user_id=user_a.id).delete()
            db.session.commit()

        # 1. Send chat message
        res = auth_client_a.post("/chat", json={"message": "I had 2 rotis and 1 cup of coffee for breakfast"})
        assert res.status_code == 200
        data = res.get_json()
        assert "reply" in data
        assert data.get("draft") is not None
        assert data["draft"]["state"] == "awaiting_confirmation"
        draft_id = data["draft"]["draft_id"]

        # 2. Get active draft
        res_act = auth_client_a.get("/chat/draft/active")
        assert res_act.status_code == 200
        act_data = res_act.get_json()
        assert act_data["active_draft"]["draft_id"] == draft_id

        # 3. Confirm draft
        res_conf = auth_client_a.post("/chat/draft/confirm", json={"draft_id": draft_id})
        assert res_conf.status_code == 200
        conf_data = res_conf.get_json()
        assert conf_data["success"] is True

        # 4. Check active draft is now null
        res_act2 = auth_client_a.get("/chat/draft/active")
        assert res_act2.status_code == 200
        assert res_act2.get_json()["active_draft"] is None

    def test_cross_user_draft_isolation(self, client, user_a, user_b, db):
        """User B cannot confirm, cancel, or edit User A's draft."""
        with client.application.app_context():
            FoodLog.query.filter(FoodLog.user_id.in_([user_a.id, user_b.id])).delete()
            PendingLogDraft.query.filter(PendingLogDraft.user_id.in_([user_a.id, user_b.id])).delete()

            # 1. User A has a pending draft in DB
            draft_a = PendingLogDraft(
                draft_id="isolated-draft-a-999",
                user_id=user_a.id,
                log_type="food",
                state="awaiting_confirmation",
                draft_data=json.dumps({
                    "meal": "Lunch",
                    "date": "2026-10-24",
                    "items": [{"food": "Chapati", "qty": 2.0, "calories": 180.0, "protein": 6.0, "fat": 6.0, "sugar": 0.0, "provenance": "catalog", "is_estimate": False}]
                })
            )
            db.session.add(draft_a)
            db.session.commit()

            # Direct function-level cross-user isolation test
            res_func_conf = confirm_draft("isolated-draft-a-999", user_b.id)
            assert res_func_conf["success"] is False
            assert res_func_conf["code"] == 404

            res_func_canc = cancel_draft("isolated-draft-a-999", user_b.id)
            assert res_func_canc["success"] is False
            assert res_func_canc["code"] == 404

            res_func_edit = edit_draft("isolated-draft-a-999", user_b.id, {"meal": "Dinner"})
            assert res_func_edit["success"] is False
            assert res_func_edit["code"] == 404

        # 2. HTTP Endpoint cross-user isolation test: log in as User B
        login(client, email="conv_user_b@example.com")

        # User B attempts to confirm User A's draft via HTTP
        res_b_conf = client.post("/chat/draft/confirm", json={"draft_id": "isolated-draft-a-999"})
        assert res_b_conf.status_code in [404, 403, 400]
        assert res_b_conf.get_json()["success"] is False

        # User B attempts to cancel User A's draft via HTTP
        res_b_canc = client.post("/chat/draft/cancel", json={"draft_id": "isolated-draft-a-999"})
        assert res_b_canc.status_code in [404, 403, 400]
        assert res_b_canc.get_json()["success"] is False

        # User B attempts to edit User A's draft via HTTP
        res_b_edit = client.post("/chat/draft/edit", json={"draft_id": "isolated-draft-a-999", "updates": {"meal": "Dinner"}})
        assert res_b_edit.status_code in [404, 403, 400]
        assert res_b_edit.get_json()["success"] is False

    def test_unauthenticated_requests_blocked(self, client):
        """Unauthenticated requests are rejected."""
        res1 = client.post("/chat", json={"message": "I had 2 rotis"})
        assert res1.status_code in [302, 401]

        res2 = client.post("/chat/draft/confirm", json={"draft_id": "test-123"})
        assert res2.status_code in [302, 401]

        res3 = client.get("/chat/draft/active")
        assert res3.status_code in [302, 401]

    def test_general_chat_fallback(self, auth_client_a, user_a, db):
        """General chat questions do not create drafts."""
        with auth_client_a.application.app_context():
            PendingLogDraft.query.filter_by(user_id=user_a.id).delete()
            db.session.commit()

        # When GROQ_API_KEY is not configured in test environment, it returns 503 or friendly fallback
        res = auth_client_a.post("/chat", json={"message": "Can you give me tips on how to improve my posture?"})
        # If GROQ_API_KEY is not set, dashboard returns 503: AI Chatbot is not configured
        if res.status_code == 503:
            data = res.get_json()
            assert "AI Chatbot is not configured" in data.get("reply", "")
        else:
            assert res.status_code == 200
            data = res.get_json()
            assert data.get("draft") is None


# ===========================================================================
# 4. Portion Detection, Scaling & Intent Separation (Milestone I)
# ===========================================================================

class TestFoodNameValidation:
    def test_valid_foods_accepted(self):
        assert is_valid_food_name("boiled eggs") is True
        assert is_valid_food_name("chapati") is True
        assert is_valid_food_name("chicken breast") is True
        assert is_valid_food_name("dal tadka") is True
        assert is_valid_food_name("grandma stew") is True
        assert is_valid_food_name("protein powder") is True

    def test_commands_and_filler_rejected(self):
        assert is_valid_food_name("log it") is False
        assert is_valid_food_name("Log It") is False
        assert is_valid_food_name("save it") is False
        assert is_valid_food_name("confirm") is False
        assert is_valid_food_name("cancel") is False
        assert is_valid_food_name("yes") is False
        assert is_valid_food_name("no") is False
        assert is_valid_food_name("thanks") is False
        assert is_valid_food_name("done") is False
        assert is_valid_food_name("please log") is False
        assert is_valid_food_name("that's correct") is False


class TestPortionDetectionAndScaling:
    def test_explicit_counts(self, app):
        with app.app_context():
            res1 = parse_food_rule_based("2 boiled eggs")
            assert len(res1["items"]) == 1
            assert res1["items"][0]["food"] == "Boiled Eggs"
            assert res1["items"][0]["qty"] == 2.0
            assert res1["items"][0]["has_quantity"] is True
            assert res1["items"][0]["calories"] == 156.0
            assert len(res1["missing_fields"]) == 0

            res2 = parse_food_rule_based("3 chapatis")
            assert len(res2["items"]) == 1
            assert res2["items"][0]["food"] == "Chapati"
            assert res2["items"][0]["qty"] == 3.0
            assert res2["items"][0]["has_quantity"] is True
            assert res2["items"][0]["calories"] == 270.0
            assert len(res2["missing_fields"]) == 0

    def test_volume_and_weight_scaling(self, app):
        with app.app_context():
            # Milk 250ml: base 200ml = 120 kcal -> 250ml = 1.25 * 120 = 150 kcal
            res_milk = parse_food_rule_based("250 ml milk")
            assert len(res_milk["items"]) == 1
            assert "Milk" in res_milk["items"][0]["food"]
            assert res_milk["items"][0]["qty"] == 1.25
            assert res_milk["items"][0]["calories"] == 150.0
            assert res_milk["items"][0]["has_quantity"] is True
            assert len(res_milk["missing_fields"]) == 0

            # Chicken 150g: base 100g = 220 kcal -> 150g = 1.5 * 220 = 330 kcal
            res_chk = parse_food_rule_based("150 g chicken")
            assert len(res_chk["items"]) == 1
            assert "Chicken" in res_chk["items"][0]["food"]
            assert res_chk["items"][0]["qty"] == 1.5
            assert res_chk["items"][0]["calories"] == 330.0
            assert res_chk["items"][0]["has_quantity"] is True
            assert len(res_chk["missing_fields"]) == 0

    def test_household_portions(self, app):
        with app.app_context():
            # 1 bowl of dal
            res_dal = parse_food_rule_based("1 bowl of dal")
            assert len(res_dal["items"]) == 1
            assert res_dal["items"][0]["food"] == "Dal Tadka"
            assert res_dal["items"][0]["qty"] == 1.0
            assert res_dal["items"][0]["has_quantity"] is True
            assert res_dal["items"][0]["calories"] == 180.0
            assert len(res_dal["missing_fields"]) == 0

            # A plate of rice
            res_rice = parse_food_rule_based("A plate of rice")
            assert len(res_rice["items"]) == 1
            assert "Rice" in res_rice["items"][0]["food"]
            assert res_rice["items"][0]["qty"] == 1.0
            assert res_rice["items"][0]["has_quantity"] is True
            assert len(res_rice["missing_fields"]) == 0

            # A handful of almonds
            res_alm = parse_food_rule_based("A handful of almonds")
            assert len(res_alm["items"]) == 1
            assert res_alm["items"][0]["food"] == "Nuts (Handful)"
            assert res_alm["items"][0]["qty"] == 1.0
            assert res_alm["items"][0]["calories"] == 170.0
            assert res_alm["items"][0]["has_quantity"] is True
            assert len(res_alm["missing_fields"]) == 0

            # One scoop of protein powder
            res_pro = parse_food_rule_based("One scoop of protein powder")
            assert len(res_pro["items"]) == 1
            assert res_pro["items"][0]["food"] == "Protein Shake (Water)"
            assert res_pro["items"][0]["qty"] == 1.0
            assert res_pro["items"][0]["calories"] == 150.0
            assert res_pro["items"][0]["has_quantity"] is True
            assert len(res_pro["missing_fields"]) == 0

    def test_mixed_meal_standard_serving_disclosure_rule_d(self, app):
        with app.app_context():
            # "2 chapatis, 2 boiled eggs, and dal"
            # Since chapatis & eggs have explicit quantities, dal should use disclosed standard serving without blocking confirmation!
            res = parse_food_rule_based("2 chapatis, 2 boiled eggs, and dal")
            assert len(res["items"]) == 3
            foods = {it["food"]: it for it in res["items"]}
            assert "Chapati" in foods
            assert "Boiled Eggs" in foods
            assert "Dal Tadka" in foods
            assert all(it["has_quantity"] is True for it in res["items"])
            assert "standard estimate" in foods["Dal Tadka"]["serving_desc"]
            assert len(res["missing_fields"]) == 0

    def test_ambiguous_all_unquantified_triggers_clarification_rule_c(self, app):
        with app.app_context():
            res = parse_food_rule_based("I ate rice and chicken")
            assert len(res["items"]) == 2
            assert all(it["has_quantity"] is False for it in res["items"])
            assert len(res["missing_fields"]) > 0


class TestConversationalCommandAndIntentSeparation:
    def test_log_it_with_no_active_draft_creates_no_records(self, app, user_a, db):
        with app.app_context():
            FoodLog.query.filter_by(user_id=user_a.id).delete()
            PendingLogDraft.query.filter_by(user_id=user_a.id).delete()
            db.session.commit()

            res = process_conversational_message(user_a.id, "Log it")
            assert "no pending meal or workout draft" in res["reply"].lower()
            assert res.get("draft") is None

            # Confirm 0 food records and 0 drafts created
            assert FoodLog.query.filter_by(user_id=user_a.id).count() == 0
            assert PendingLogDraft.query.filter_by(user_id=user_a.id).count() == 0

    def test_log_it_confirms_existing_draft_and_never_creates_food_named_log_it(self, app, user_a, db):
        with app.app_context():
            FoodLog.query.filter_by(user_id=user_a.id).delete()
            PendingLogDraft.query.filter_by(user_id=user_a.id).delete()
            db.session.commit()

            # 1. User states meal
            res1 = process_conversational_message(user_a.id, "2 chapatis and 2 boiled eggs for dinner")
            assert res1["draft"]["state"] == "awaiting_confirmation"

            # 2. User confirms by saying "Log it"
            res2 = process_conversational_message(user_a.id, "Log it")
            assert res2["success"] is True
            assert res2["draft"]["state"] == "confirmed"

            # 3. Check database logs
            logs = FoodLog.query.filter_by(user_id=user_a.id).all()
            assert len(logs) == 2
            names = [l.food for l in logs]
            assert "Chapati" in names
            assert "Boiled Eggs" in names
            # MUST NEVER contain "Log It"
            assert not any("log it" in n.lower() for n in names)

    def test_log_it_on_collecting_draft_applies_standard_servings_and_confirms(self, app, user_a, db):
        with app.app_context():
            FoodLog.query.filter_by(user_id=user_a.id).delete()
            PendingLogDraft.query.filter_by(user_id=user_a.id).delete()
            db.session.commit()

            # 1. Unquantified meal -> collecting state
            res1 = process_conversational_message(user_a.id, "I ate rice and chicken")
            assert res1["draft"]["state"] == "collecting"

            # 2. User says "Log it"
            res2 = process_conversational_message(user_a.id, "Log it")
            assert res2["success"] is True
            assert res2["draft"]["state"] == "confirmed"

            # 3. Check database: saved with standard servings, no food named "Log It"
            logs = FoodLog.query.filter_by(user_id=user_a.id).all()
            assert len(logs) == 2
            names = [l.food for l in logs]
            assert not any("log it" in n.lower() for n in names)

    def test_cancel_with_no_active_draft_creates_no_records(self, app, user_a, db):
        with app.app_context():
            FoodLog.query.filter_by(user_id=user_a.id).delete()
            PendingLogDraft.query.filter_by(user_id=user_a.id).delete()
            db.session.commit()

            res = process_conversational_message(user_a.id, "Cancel")
            assert "no pending meal or workout draft" in res["reply"].lower()
            assert res.get("draft") is None
            assert FoodLog.query.filter_by(user_id=user_a.id).count() == 0

    def test_corrections_rule_e(self, app, user_a, db):
        with app.app_context():
            FoodLog.query.filter_by(user_id=user_a.id).delete()
            PendingLogDraft.query.filter_by(user_id=user_a.id).delete()
            db.session.commit()

            # Start with 2 boiled eggs and coffee
            res1 = process_conversational_message(user_a.id, "2 boiled eggs and 1 cup of coffee for breakfast")
            assert res1["draft"]["state"] == "awaiting_confirmation"

            # Correction 1: "I had three eggs, not two"
            res2 = process_conversational_message(user_a.id, "I had three eggs, not two")
            draft2 = res2["draft"]
            items2 = draft2["data"]["items"]
            # Should have exactly 2 items (Boiled Eggs and Coffee), NOT 3
            assert len(items2) == 2
            eggs_item = next(it for it in items2 if "Egg" in it["food"])
            assert eggs_item["qty"] == 3.0
            assert eggs_item["calories"] == 234.0  # 78 * 3

            # Correction 2: "The coffee had no sugar"
            res3 = process_conversational_message(user_a.id, "The coffee had no sugar")
            draft3 = res3["draft"]
            items3 = draft3["data"]["items"]
            coffee_item = next(it for it in items3 if "Coffee" in it["food"])
            assert coffee_item["sugar"] == 0.0
            assert coffee_item["calories"] < 90.0

            # Confirmation
            res4 = process_conversational_message(user_a.id, "Save this meal")
            assert res4["success"] is True
            saved = FoodLog.query.filter_by(user_id=user_a.id).all()
            assert len(saved) == 2
            saved_eggs = next(l for l in saved if "Egg" in l.food)
            assert saved_eggs.qty == 3.0

    def test_use_standard_serving_resolves_collecting_draft(self, app, user_a, db):
        with app.app_context():
            FoodLog.query.filter_by(user_id=user_a.id).delete()
            PendingLogDraft.query.filter_by(user_id=user_a.id).delete()
            db.session.commit()

            # Genuinely ambiguous input
            res1 = process_conversational_message(user_a.id, "I ate rice and chicken")
            assert res1["draft"]["state"] == "collecting"

            # User says "Use one standard serving"
            res2 = process_conversational_message(user_a.id, "Use one standard serving")
            assert res2["draft"]["state"] == "awaiting_confirmation"
            items = res2["draft"]["data"]["items"]
            assert all(it["has_quantity"] is True for it in items)
            assert res2["draft"]["missing_fields"] == []
