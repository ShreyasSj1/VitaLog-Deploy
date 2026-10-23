"""Unit tests for ORM models and the seed_lookup_tables function."""
import pytest
from tests.conftest import make_user
from constants import FOOD_DATA, EXERCISE_CATALOG


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------

class TestUserModel:
    def test_create_user(self, db):
        user = make_user(db)
        from models import User
        found = User.query.filter_by(email="test@example.com").first()
        assert found is not None
        assert found.name == "Test User"

    def test_user_is_active_defaults_true(self, db):
        user = make_user(db, email="active@example.com")
        assert user.is_active == 1

    def test_user_role_defaults_to_user_even_when_first(self, db):
        """First user in an empty DB should NOT automatically become admin."""
        from models import User, default_role_for_email
        User.query.delete()
        db.session.commit()
        role = default_role_for_email("first@example.com")
        assert role == "user"

    def test_user_role_admin_when_in_admin_emails(self, monkeypatch):
        from models import default_role_for_email
        monkeypatch.setenv("ADMIN_EMAILS", "superadmin@example.com,ops@example.com")
        assert default_role_for_email("superadmin@example.com") == "admin"
        assert default_role_for_email("OPS@EXAMPLE.COM") == "admin"
        assert default_role_for_email("regular@example.com") == "user"

    def test_get_user_by_email(self, db):
        make_user(db, email="lookup@example.com")
        from models import get_user_by_email
        user = get_user_by_email("lookup@example.com")
        assert user is not None
        assert user.email == "lookup@example.com"

    def test_get_user_by_email_case_insensitive(self, db):
        make_user(db, email="case@example.com")
        from models import get_user_by_email
        user = get_user_by_email("CASE@EXAMPLE.COM")
        assert user is not None

    def test_get_user_by_id(self, db):
        user = make_user(db, email="byid@example.com")
        from models import get_user_by_id
        found = get_user_by_id(user.id)
        assert found is not None
        assert found.email == "byid@example.com"


# ---------------------------------------------------------------------------
# create_user helper
# ---------------------------------------------------------------------------

class TestCreateUser:
    def test_create_user_success(self, db):
        from models import create_user, User
        User.query.delete()
        db.session.commit()
        user, err = create_user("Alice", "alice@example.com", "Secret123!")
        assert err is None
        assert user is not None
        assert user.email == "alice@example.com"

    def test_create_user_duplicate_email(self, db):
        from models import create_user
        create_user("Bob", "bob@example.com", "Secret123!")
        user, err = create_user("Bob2", "bob@example.com", "Other456!")
        assert user is None
        assert "already exists" in err


# ---------------------------------------------------------------------------
# FoodItem lookup table
# ---------------------------------------------------------------------------

class TestFoodItemTable:
    def test_food_items_seeded(self, db):
        from models import FoodItem
        count = FoodItem.query.count()
        # Should have at least all items from FOOD_DATA
        total_expected = sum(len(v) for v in FOOD_DATA.values())
        assert count >= total_expected

    def test_food_item_has_correct_data(self, db):
        from models import FoodItem
        item = FoodItem.query.filter_by(
            meal_category="Breakfast", name="Idli"
        ).first()
        assert item is not None
        assert item.calories == pytest.approx(45)
        assert item.protein == pytest.approx(2)

    def test_food_item_to_dict(self, db):
        from models import FoodItem
        item = FoodItem.query.filter_by(name="Banana").first()
        d = item.to_dict()
        assert "meal_category" in d
        assert "calories" in d
        assert d["is_custom"] is False

    def test_seed_is_idempotent(self, db):
        """Calling seed again should not create duplicates."""
        from models import FoodItem, seed_lookup_tables
        before = FoodItem.query.count()
        seed_lookup_tables()
        after = FoodItem.query.count()
        assert before == after


# ---------------------------------------------------------------------------
# Exercise lookup table
# ---------------------------------------------------------------------------

class TestExerciseTable:
    def test_exercises_seeded(self, db):
        from models import Exercise
        count = Exercise.query.count()
        total_expected = sum(len(v) for v in EXERCISE_CATALOG.values())
        assert count >= total_expected

    def test_cardio_exercise_flagged(self, db):
        from models import Exercise
        ex = Exercise.query.filter_by(name="Treadmill (Running)").first()
        assert ex is not None
        assert ex.is_cardio is True

    def test_cardio_exercise_has_meta(self, db):
        import json
        from models import Exercise
        ex = Exercise.query.filter_by(name="Cycling").first()
        assert ex.cardio_meta is not None
        meta = json.loads(ex.cardio_meta)
        assert "met" in meta
        assert "baseline_speed" in meta

    def test_strength_exercise_not_cardio(self, db):
        from models import Exercise
        ex = Exercise.query.filter_by(name="Bench Press").first()
        assert ex is not None
        assert ex.is_cardio is False
        assert ex.cardio_meta is None

    def test_exercise_to_dict(self, db):
        from models import Exercise
        ex = Exercise.query.filter_by(name="Squat").first()
        d = ex.to_dict()
        assert d["muscle_group"] == "Legs"
        assert d["is_custom"] is False
