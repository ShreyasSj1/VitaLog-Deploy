"""Integration tests for nutrition favorites and saved meals."""
from datetime import date
import pytest
from tests.conftest import make_user, login
from models import FoodFavorite, SavedMeal, SavedMealItem, FoodLog, User

TODAY = date.today().isoformat()


class TestNutritionFavoritesAndSavedMeals:
    def test_favorite_toggle(self, client, db):
        user = make_user(db, email="fav_user@example.com")
        login(client, email="fav_user@example.com")

        # Add favorite
        resp = client.post(
            "/api/food/favorite",
            json={"meal_category": "Breakfast", "name": "Oatmeal"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["is_favorite"] is True

        fav = FoodFavorite.query.filter_by(user_id=user.id, meal_category="Breakfast", name="Oatmeal").first()
        assert fav is not None

        # Remove favorite (toggle)
        resp2 = client.post(
            "/api/food/favorite",
            json={"meal_category": "Breakfast", "name": "Oatmeal"},
        )
        assert resp2.status_code == 200
        assert resp2.get_json()["is_favorite"] is False
        assert FoodFavorite.query.filter_by(user_id=user.id, meal_category="Breakfast", name="Oatmeal").first() is None

    def test_food_recents_api(self, client, db):
        user = make_user(db, email="recents_user@example.com")
        login(client, email="recents_user@example.com")

        # Log some food
        client.post(f"/food?date={TODAY}", data={"meal": "Breakfast", "food": "Idli", "qty": "2", "date": TODAY})
        client.post(f"/food?date={TODAY}", data={"meal": "Breakfast", "food": "Boiled Eggs", "qty": "3", "date": TODAY})

        resp = client.get("/api/food/recents?category=Breakfast")
        assert resp.status_code == 200
        recents = resp.get_json()["recents"]
        names = [r["name"] for r in recents]
        assert "Idli" in names
        assert "Boiled Eggs" in names

    def test_create_and_log_saved_meal(self, client, db):
        user = make_user(db, email="saved_meal@example.com")
        login(client, email="saved_meal@example.com")

        # 1. Create saved meal combo
        resp = client.post(
            "/saved-meals/create",
            json={
                "name": "Power Breakfast",
                "meal_category": "Breakfast",
                "notes": "Pre-workout breakfast",
                "items": [
                    {"food": "Eggs", "qty": 3, "calories": 210, "protein": 18, "fat": 15, "sugar": 1},
                    {"food": "Oatmeal", "qty": 1, "calories": 150, "protein": 5, "fat": 3, "sugar": 1},
                ],
            },
        )
        assert resp.status_code == 200
        meal_id = resp.get_json()["meal"]["id"]

        saved_meal = db.session.get(SavedMeal, meal_id)
        assert saved_meal is not None
        assert len(saved_meal.items) == 2

        # 2. View saved meals endpoint
        page_resp = client.get("/saved-meals")
        assert page_resp.status_code == 200
        data = page_resp.get_json()
        assert any(m["name"] == "Power Breakfast" for m in data["saved_meals"])

        # 3. 1-click log the saved meal
        log_resp = client.post(
            f"/saved-meals/log/{meal_id}",
            json={"date": TODAY},
        )
        assert log_resp.status_code == 200
        assert log_resp.get_json()["success"] is True

        # Verify FoodLogs created
        food_logs = FoodLog.query.filter_by(user_id=user.id, date=TODAY).all()
        assert len(food_logs) == 2
        logged_foods = [l.food for l in food_logs]
        assert "Eggs" in logged_foods
        assert "Oatmeal" in logged_foods

        # 4. Delete saved meal
        del_resp = client.post(f"/saved-meals/delete/{meal_id}", follow_redirects=True)
        assert del_resp.status_code == 200
        assert db.session.get(SavedMeal, meal_id) is None
