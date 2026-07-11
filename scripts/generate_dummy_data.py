"""
scripts/generate_dummy_data.py

Idempotently creates two test users ('athlete@example.com' and 'wellness@example.com')
and populates their logs for the past 7 days with realistic, high-fidelity data
to demonstrate the application's visualization and health score algorithms.
"""

import sys
from datetime import date, timedelta
from werkzeug.security import generate_password_hash

# Ensure project root is in the path
from pathlib import Path
project_root = Path(__file__).resolve().parents[1]
sys.path.append(str(project_root))

from app import app
from extensions import db
from models import User, FoodLog, SleepLog, WellbeingLog, GymLog, FoodItem, Exercise
from constants import MUSCLE_FACTORS, INTENSITY_MAP

USERS_DATA = {
    "athlete@example.com": {
        "name": "Athlete User",
        "password": "Password123!",
        "age": 25,
        "height": 180.0,
        "weight": 80.0,
        "goal_calories": 2500.0,
        "goal_protein": 180.0,
        "goal_fat": 70.0,
        "goal_sugar": 40.0,
    },
    "wellness@example.com": {
        "name": "Wellness User",
        "password": "Password123!",
        "age": 30,
        "height": 165.0,
        "weight": 65.0,
        "goal_calories": 1600.0,
        "goal_protein": 90.0,
        "goal_fat": 50.0,
        "goal_sugar": 30.0,
    }
}

def create_or_get_user(email, info):
    user = User.query.filter_by(email=email).first()
    if not user:
        print(f"Creating user {email}...")
        user = User(
            email=email,
            password_hash=generate_password_hash(info["password"]),
            name=info["name"],
            age=info["age"],
            height=info["height"],
            weight=info["weight"],
            role="user",
            is_active=1,
            goal_calories=info["goal_calories"],
            goal_protein=info["goal_protein"],
            goal_fat=info["goal_fat"],
            goal_sugar=info["goal_sugar"]
        )
        db.session.add(user)
        db.session.commit()
    else:
        print(f"User {email} already exists. Updating profile details...")
        user.name = info["name"]
        user.age = info["age"]
        user.height = info["height"]
        user.weight = info["weight"]
        user.goal_calories = info["goal_calories"]
        user.goal_protein = info["goal_protein"]
        user.goal_fat = info["goal_fat"]
        user.goal_sugar = info["goal_sugar"]
        db.session.commit()
    return user

def clear_existing_logs(user_id, start_date_s, end_date_s):
    FoodLog.query.filter(FoodLog.user_id == user_id, FoodLog.date >= start_date_s, FoodLog.date <= end_date_s).delete()
    SleepLog.query.filter(SleepLog.user_id == user_id, SleepLog.date >= start_date_s, SleepLog.date <= end_date_s).delete()
    WellbeingLog.query.filter(WellbeingLog.user_id == user_id, WellbeingLog.date >= start_date_s, WellbeingLog.date <= end_date_s).delete()
    GymLog.query.filter(GymLog.user_id == user_id, GymLog.date >= start_date_s, GymLog.date <= end_date_s).delete()
    db.session.commit()

def populate_athlete(user, dates):
    print("Populating logs for Athlete User...")
    
    # Pre-fetch lookup foods to compute nutritional weights
    # Structure: FOOD_LOOKUP[category][name] = FoodItem
    foods = FoodItem.query.all()
    food_map = {}
    for f in foods:
        food_map.setdefault(f.meal_category, {})[f.name] = f

    for i, dt in enumerate(dates):
        dt_s = dt.isoformat()
        
        # 1. Food logs
        # Vary quantities slightly
        q_mul = 1.0 + (i % 3) * 0.15 
        
        # Breakfast
        if i % 2 == 0:
            add_food_log(user.id, dt_s, "Breakfast", "Omelette", 2.0 * q_mul, food_map)
            add_food_log(user.id, dt_s, "Breakfast", "Milk (200ml)", 1.5 * q_mul, food_map)
        else:
            add_food_log(user.id, dt_s, "Breakfast", "Masala Dosa", 1.5 * q_mul, food_map)
            add_food_log(user.id, dt_s, "Breakfast", "Tea / Coffee", 1.0, food_map)

        # Lunch
        if i % 3 == 0:
            add_food_log(user.id, dt_s, "Lunch", "Chicken Biryani", 1.5 * q_mul, food_map)
            add_food_log(user.id, dt_s, "Lunch", "Curd (Plain)", 1.0, food_map)
        else:
            add_food_log(user.id, dt_s, "Lunch", "Chapati", 3.0, food_map)
            add_food_log(user.id, dt_s, "Lunch", "Chicken Curry", 1.5 * q_mul, food_map)
            add_food_log(user.id, dt_s, "Lunch", "Dal Tadka", 1.0, food_map)

        # Pre/Post Workout
        add_food_log(user.id, dt_s, "Pre/Post Workout", "Protein Shake (Water)", 1.5, food_map)
        if i % 2 == 0:
            add_food_log(user.id, dt_s, "Pre/Post Workout", "Peanut Butter Sandwich", 1.0, food_map)
        else:
            add_food_log(user.id, dt_s, "Pre/Post Workout", "Banana", 1.0, food_map)

        # Dinner
        if i % 2 == 0:
            add_food_log(user.id, dt_s, "Dinner", "Grilled Chicken", 1.5 * q_mul, food_map)
            add_food_log(user.id, dt_s, "Dinner", "Salad", 1.0, food_map)
        else:
            add_food_log(user.id, dt_s, "Dinner", "Plain Rice", 1.5 * q_mul, food_map)
            add_food_log(user.id, dt_s, "Dinner", "Fish Curry", 1.2 * q_mul, food_map)

        # Snacks
        add_food_log(user.id, dt_s, "Snacks", "Nuts (Handful)", 1.0, food_map)
        
        # 2. Sleep logs
        hours = 7.5 + (i % 3) * 0.4
        quality = 4 if i % 2 == 0 else 5
        notes = "Felt recovered." if quality == 5 else "Slightly interrupted sleep."
        db.session.add(SleepLog(user_id=user.id, date=dt_s, hours=hours, quality=quality, notes=notes))

        # 3. Wellbeing logs
        db.session.add(WellbeingLog(user_id=user.id, date=dt_s, activity="Stretching", minutes=15))
        if i % 2 == 0:
            db.session.add(WellbeingLog(user_id=user.id, date=dt_s, activity="Reading", minutes=20))

        # 4. Gym logs (Rotate workouts)
        w_day = i % 7
        if w_day == 0: # Chest
            add_strength_gym(user.id, dt_s, "Chest", "Bench Press", 4, 10, 80.0, "Hard")
            add_strength_gym(user.id, dt_s, "Chest", "Dumbbell Fly", 3, 12, 20.0, "Medium")
            add_strength_gym(user.id, dt_s, "Chest", "Push-Ups", 3, 20, 0.0, "Medium")
        elif w_day == 1: # Back
            add_strength_gym(user.id, dt_s, "Back", "Deadlift", 3, 8, 110.0, "Hard")
            add_strength_gym(user.id, dt_s, "Back", "Pull-Ups", 4, 8, 0.0, "Hard")
            add_strength_gym(user.id, dt_s, "Back", "Seated Cable Row", 3, 12, 60.0, "Medium")
        elif w_day == 2: # Legs
            add_strength_gym(user.id, dt_s, "Legs", "Squat", 4, 8, 90.0, "Hard")
            add_strength_gym(user.id, dt_s, "Legs", "Leg Press", 3, 10, 160.0, "Medium")
            add_strength_gym(user.id, dt_s, "Legs", "Calf Raises", 3, 15, 40.0, "Easy")
        elif w_day == 3: # Shoulders
            add_strength_gym(user.id, dt_s, "Shoulders", "Overhead Press", 3, 8, 45.0, "Hard")
            add_strength_gym(user.id, dt_s, "Shoulders", "Lateral Raises", 4, 12, 10.0, "Medium")
            add_strength_gym(user.id, dt_s, "Shoulders", "Shrugs", 3, 10, 60.0, "Easy")
        elif w_day == 4: # Arms
            add_strength_gym(user.id, dt_s, "Arms", "Bicep Curl", 3, 10, 15.0, "Medium")
            add_strength_gym(user.id, dt_s, "Arms", "Tricep Pushdown", 3, 12, 25.0, "Medium")
            add_strength_gym(user.id, dt_s, "Arms", "Hammer Curl", 3, 10, 12.5, "Easy")
        elif w_day == 5: # Cardio
            add_cardio_gym(user.id, dt_s, "Cardio", "Treadmill (Running)", 30.0, 10.5, 0.0, "Hard", user.weight)
        elif w_day == 6: # Rest & Core
            add_strength_gym(user.id, dt_s, "Core", "Plank", 3, 60, 0.0, "Medium") # 60 seconds reps mock
            add_strength_gym(user.id, dt_s, "Core", "Bicycle Crunches", 3, 20, 0.0, "Easy")
            add_cardio_gym(user.id, dt_s, "Cardio", "Cycling", 20.0, 18.0, 0.0, "Medium", user.weight)

    db.session.commit()

def populate_wellness(user, dates):
    print("Populating logs for Wellness User...")
    
    foods = FoodItem.query.all()
    food_map = {}
    for f in foods:
        food_map.setdefault(f.meal_category, {})[f.name] = f

    for i, dt in enumerate(dates):
        dt_s = dt.isoformat()
        
        # 1. Food logs
        q_mul = 0.9 + (i % 2) * 0.1
        
        # Breakfast
        if i % 2 == 0:
            add_food_log(user.id, dt_s, "Breakfast", "Idli", 3.0 * q_mul, food_map)
            add_food_log(user.id, dt_s, "Breakfast", "Tea / Coffee", 1.0, food_map)
        else:
            add_food_log(user.id, dt_s, "Breakfast", "Upma", 1.0 * q_mul, food_map)
            add_food_log(user.id, dt_s, "Breakfast", "Tea / Coffee", 1.0, food_map)

        # Lunch
        add_food_log(user.id, dt_s, "Lunch", "Chapati", 2.0, food_map)
        add_food_log(user.id, dt_s, "Lunch", "Dal Tadka", 1.0 * q_mul, food_map)
        add_food_log(user.id, dt_s, "Lunch", "Curd (Plain)", 1.0, food_map)

        # Pre/Post Workout
        if i % 2 == 0:
            add_food_log(user.id, dt_s, "Pre/Post Workout", "Greek Yogurt", 1.0 * q_mul, food_map)
        else:
            add_food_log(user.id, dt_s, "Pre/Post Workout", "Banana", 1.0, food_map)

        # Dinner
        add_food_log(user.id, dt_s, "Dinner", "Vegetable Stir Fry", 1.2 * q_mul, food_map)
        add_food_log(user.id, dt_s, "Dinner", "Soup (Veg)", 1.0, food_map)
        if i % 3 == 0:
            add_food_log(user.id, dt_s, "Dinner", "Salad", 1.0, food_map)

        # Snacks
        if i % 2 == 0:
            add_food_log(user.id, dt_s, "Snacks", "Fruit Bowl", 1.0, food_map)
        else:
            add_food_log(user.id, dt_s, "Snacks", "Biscuits", 2.0, food_map)
        
        # 2. Sleep logs
        hours = 6.8 + (i % 2) * 0.6
        quality = 3 if i % 3 == 0 else 4
        notes = "Felt rested." if quality == 4 else "Tossed and turned a bit."
        db.session.add(SleepLog(user_id=user.id, date=dt_s, hours=hours, quality=quality, notes=notes))

        # 3. Wellbeing logs (Meditation daily, others rotate)
        db.session.add(WellbeingLog(user_id=user.id, date=dt_s, activity="Meditation", minutes=20))
        if i % 2 == 0:
            db.session.add(WellbeingLog(user_id=user.id, date=dt_s, activity="Journaling", minutes=15))
        if i % 3 == 0:
            db.session.add(WellbeingLog(user_id=user.id, date=dt_s, activity="Yoga", minutes=30))

        # 4. Gym logs (Focus on cardio & core)
        w_day = i % 7
        if w_day == 0:
            add_cardio_gym(user.id, dt_s, "Cardio", "Inclined Walking", 45.0, 5.5, 5.0, "Medium", user.weight)
        elif w_day == 1:
            add_strength_gym(user.id, dt_s, "Core", "Plank", 3, 45, 0.0, "Medium")
            add_strength_gym(user.id, dt_s, "Core", "Leg Raises", 3, 12, 0.0, "Easy")
        elif w_day == 2:
            add_cardio_gym(user.id, dt_s, "Cardio", "Cycling", 30.0, 16.0, 0.0, "Medium", user.weight)
        elif w_day == 3:
            add_strength_gym(user.id, dt_s, "Core", "Crunches", 3, 15, 0.0, "Easy")
            add_strength_gym(user.id, dt_s, "Core", "Russian Twists", 3, 20, 0.0, "Medium")
        elif w_day == 4:
            add_cardio_gym(user.id, dt_s, "Cardio", "Elliptical", 40.0, 7.0, 0.0, "Medium", user.weight)
        elif w_day == 5:
            pass # Rest Day
        elif w_day == 6:
            add_cardio_gym(user.id, dt_s, "Cardio", "Treadmill (Running)", 25.0, 8.5, 0.0, "Hard", user.weight)

    db.session.commit()

# --- Utility Helpers ---

def add_food_log(user_id, date_s, meal, name, qty, food_map):
    if meal in food_map and name in food_map[meal]:
        f = food_map[meal][name]
        db.session.add(FoodLog(
            user_id=user_id,
            date=date_s,
            meal=meal,
            food=f.name,
            qty=qty,
            calories=f.calories * qty,
            protein=f.protein * qty,
            fat=f.fat * qty,
            sugar=f.sugar * qty
        ))

def add_strength_gym(user_id, date_s, muscle, exercise, sets, reps, weight, intensity):
    m_factor = MUSCLE_FACTORS.get(muscle, 1.0)
    int_factor = INTENSITY_MAP.get(intensity, 1.0)
    eff_weight = weight if weight > 0 else 50
    calories = (sets * reps * eff_weight * 0.04) * m_factor * int_factor
    db.session.add(GymLog(
        user_id=user_id,
        date=date_s,
        muscle=muscle,
        exercise=exercise,
        sets=sets,
        reps=reps,
        weight=weight,
        speed=0.0,
        incline=0.0,
        intensity=intensity,
        duration=0.0,
        calories=calories
    ))

def add_cardio_gym(user_id, date_s, muscle, exercise, duration, speed, incline, intensity, body_weight):
    # Lookup cardio MET
    from constants import CARDIO_META
    meta = CARDIO_META.get(exercise, {"met": 5.0, "baseline_speed": 6.0, "speed_factor": 0.25})
    base_met = meta["met"]
    baseline_speed = meta["baseline_speed"]
    speed_factor_val = meta["speed_factor"]
    
    speed_boost = max(0, speed - baseline_speed) * speed_factor_val
    incline_boost = max(0, incline) * 0.35 if exercise == "Inclined Walking" else 0
    
    calories = ((base_met + speed_boost + incline_boost) * 3.5 * body_weight / 200) * duration
    db.session.add(GymLog(
        user_id=user_id,
        date=date_s,
        muscle=muscle,
        exercise=exercise,
        sets=0,
        reps=0,
        weight=0.0,
        speed=speed,
        incline=incline,
        intensity=intensity,
        duration=duration,
        calories=calories
    ))

def main():
    print("Initializing dummy data builder inside Flask App Context...")
    with app.app_context():
        # Retrieve users or create them
        user_ath = create_or_get_user("athlete@example.com", USERS_DATA["athlete@example.com"])
        user_wel = create_or_get_user("wellness@example.com", USERS_DATA["wellness@example.com"])

        # Dates range: 7 days ending today
        today = date.today()
        dates = [today - timedelta(days=i) for i in range(6, -1, -1)]
        start_date_s = dates[0].isoformat()
        end_date_s = dates[-1].isoformat()

        # Clear existing logs for both users in this date range to prevent doubling up
        clear_existing_logs(user_ath.id, start_date_s, end_date_s)
        clear_existing_logs(user_wel.id, start_date_s, end_date_s)

        # Generate logs
        populate_athlete(user_ath, dates)
        populate_wellness(user_wel, dates)

        print("All test data populated successfully!")

if __name__ == "__main__":
    main()
