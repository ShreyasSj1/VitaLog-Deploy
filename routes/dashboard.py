import os
import json
from datetime import date, datetime, timedelta
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, abort, flash
from flask_login import login_required, current_user
import groq
from sqlalchemy import func

from extensions import db
from models import (
    FoodLog, GymLog, SleepLog, WellbeingLog, User, FoodItem, Exercise, ChatMessage,
    WeightLog, FoodFavorite, SavedMeal, SavedMealItem, WorkoutSet, UserPreference,
    record_weight_log, get_or_create_user_preferences
)
from utils import (
    normalize_selected_date, get_week_dates, parse_optional_float, get_today,
    chat_rate_limiter, validate_positive_float, validate_non_negative_float,
    validate_int_range, validate_text, calculate_tdee
)
from constants import FOOD_DATA, CARDIO_EXERCISES, EXERCISE_CATALOG, MUSCLE_FACTORS, INTENSITY_MAP
from daily_challenges import get_daily_challenge, is_challenge_completed
from config import Config

dashboard_bp = Blueprint("dashboard", __name__)

GROQ_API_KEY = Config.GROQ_API_KEY
groq_client = None
if GROQ_API_KEY:
    groq_client = groq.Groq(api_key=GROQ_API_KEY)

def get_groq_client():
    global groq_client
    if groq_client is not None:
        return groq_client
    api_key = os.environ.get("GROQ_API_KEY") or Config.GROQ_API_KEY
    if api_key:
        groq_client = groq.Groq(api_key=api_key)
    return groq_client

def is_cardio_exercise(exercise_name):
    return exercise_name in CARDIO_EXERCISES

def is_admin_user():
    return (getattr(current_user, "role", "") or "").lower() == "admin"

@dashboard_bp.route("/health")
def health():
    return {"ok": True, "status": "healthy"}, 200

@dashboard_bp.route("/service-worker.js")
def service_worker():
    from flask import current_app, make_response
    response = make_response(current_app.send_static_file("service-worker.js"))
    response.headers["Content-Type"] = "application/javascript"
    response.headers["Service-Worker-Allowed"] = "/"
    return response

@dashboard_bp.route("/manifest.json")
def manifest():
    from flask import current_app
    return current_app.send_static_file("manifest.json")

@dashboard_bp.route("/offline")
def offline():
    return render_template("offline.html")

@dashboard_bp.route("/")
@login_required
def index():
    selected_date = normalize_selected_date(request.args.get("date"))
    week = get_week_dates(selected_date)

    totals = db.session.query(
        func.coalesce(func.sum(FoodLog.calories), 0).label('cal'),
        func.coalesce(func.sum(FoodLog.protein), 0).label('protein'),
        func.coalesce(func.sum(FoodLog.fat), 0).label('fat'),
        func.coalesce(func.sum(FoodLog.sugar), 0).label('sugar')
    ).filter(FoodLog.user_id == current_user.id, FoodLog.date == selected_date).first()

    gym_total = db.session.query(func.coalesce(func.sum(GymLog.calories), 0)) \
        .filter(GymLog.user_id == current_user.id, GymLog.date == selected_date).scalar() or 0

    gym_duration = db.session.query(func.coalesce(func.sum(GymLog.duration), 0)) \
        .filter(GymLog.user_id == current_user.id, GymLog.date == selected_date).scalar() or 0

    # ── Optimized Weekly Aggregations (Single Grouped Queries - No N+1) ──
    food_by_date = dict(
        db.session.query(FoodLog.date, func.coalesce(func.sum(FoodLog.calories), 0))
        .filter(FoodLog.user_id == current_user.id, FoodLog.date.in_(week))
        .group_by(FoodLog.date).all()
    )
    sleep_by_date = {
        row.date: row.hours
        for row in SleepLog.query.filter(SleepLog.user_id == current_user.id, SleepLog.date.in_(week)).all()
    }
    wb_by_date = dict(
        db.session.query(WellbeingLog.date, func.coalesce(func.sum(WellbeingLog.minutes), 0))
        .filter(WellbeingLog.user_id == current_user.id, WellbeingLog.date.in_(week))
        .group_by(WellbeingLog.date).all()
    )
    gym_by_date = dict(
        db.session.query(GymLog.date, func.coalesce(func.sum(GymLog.calories), 0))
        .filter(GymLog.user_id == current_user.id, GymLog.date.in_(week))
        .group_by(GymLog.date).all()
    )

    weekly_cal = [round(float(food_by_date.get(d, 0) or 0), 1) for d in week]
    weekly_sleep = [round(float(sleep_by_date.get(d, 0) or 0), 1) for d in week]
    weekly_wellbeing = [int(wb_by_date.get(d, 0) or 0) for d in week]
    weekly_gym = [round(float(gym_by_date.get(d, 0) or 0), 1) for d in week]

    goals = current_user.goals
    has_custom_goals = bool(current_user.goal_calories is not None)

    # ── Trustworthy Energy Balance & TDEE ──
    estimated_tdee = None
    energy_balance = None
    if current_user.weight and current_user.height and current_user.age:
        pref = getattr(current_user, "preferences", None)
        gender = pref.gender if pref else "unspecified"
        act_level = pref.activity_level if pref else "moderate"
        act_factors = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725}
        act_factor = act_factors.get(act_level, 1.375)
        estimated_tdee = calculate_tdee(current_user.weight, current_user.height, current_user.age, gender, act_factor)
        energy_balance = round(totals.cal - (estimated_tdee + gym_total), 1)

    # ── Daily Habits & Consistency Summary ──
    habits = []
    habits_achieved = 0.0
    total_habits = 4

    # 1. Nutrition habit
    if totals.cal > 0:
        if totals.cal >= goals["calories"] * 0.75 and totals.cal <= goals["calories"] * 1.10:
            habits.append(("Nutrition on target", "good"))
            habits_achieved += 1.0
        elif totals.cal < goals["calories"] * 0.75:
            habits.append((f"Intake below target ({int(totals.cal)}/{int(goals['calories'])} kcal)", "neutral"))
            habits_achieved += 0.5
        else:
            habits.append(("Calorie target exceeded", "bad"))
            habits_achieved += 0.5
    else:
        habits.append(("No food logged yet today", "neutral"))

    # 2. Workout habit
    if gym_total > 0:
        habits.append((f"Workout completed ({int(gym_total)} kcal est. burn)", "good"))
        habits_achieved += 1.0
    else:
        habits.append(("Rest day / No workout logged", "neutral"))

    # 3. Sleep habit
    sleep_row = SleepLog.query.filter_by(user_id=current_user.id, date=selected_date).first()
    if sleep_row:
        if sleep_row.hours >= 7.0:
            habits.append((f"Healthy sleep duration ({sleep_row.hours} hrs)", "good"))
            habits_achieved += 1.0
        elif sleep_row.hours >= 5.0:
            habits.append((f"Moderate sleep duration ({sleep_row.hours} hrs)", "neutral"))
            habits_achieved += 0.5
        else:
            habits.append((f"Short sleep duration ({sleep_row.hours} hrs)", "bad"))
    else:
        habits.append(("Sleep not logged yet today", "neutral"))

    # 4. Wellbeing habit
    wb_today = wb_by_date.get(selected_date, 0)
    if wb_today > 0:
        habits.append((f"Mindfulness / Wellbeing ({wb_today} mins)", "good"))
        habits_achieved += 1.0
    else:
        habits.append(("Wellbeing session optional", "neutral"))

    habit_score = int(round((habits_achieved / total_habits) * 100))

    daily_challenge = get_daily_challenge(selected_date)
    challenge_completed = is_challenge_completed(current_user.id, selected_date, daily_challenge["title"])

    return render_template(
        "index.html",
        active_page="dashboard",
        selected_date=selected_date,
        goals=goals,
        has_custom_goals=has_custom_goals,
        total_calories=totals.cal,
        total_protein=totals.protein,
        total_fat=totals.fat,
        total_sugar=totals.sugar,
        gym_calories=gym_total,
        gym_duration=gym_duration,
        net_calories=totals.cal - gym_total,
        estimated_tdee=estimated_tdee,
        energy_balance=energy_balance,
        health_score=habit_score,
        health_reasons=habits,
        week=week,
        weekly_cal=weekly_cal,
        weekly_sleep=weekly_sleep,
        weekly_wellbeing=weekly_wellbeing,
        weekly_gym=weekly_gym,
        daily_challenge=daily_challenge,
        challenge_completed=challenge_completed,
        max_date=get_today().isoformat(),
    )


@dashboard_bp.route("/food", methods=["GET", "POST"])
@login_required
def food():
    selected_date = normalize_selected_date(request.args.get("date", request.form.get("date")))

    if request.method == "POST":
        meal = (request.form.get("meal") or "").strip()
        food_item_name = (request.form.get("food") or "").strip()
        try:
            qty = validate_positive_float(request.form.get("qty", 1), "Quantity", min_val=0.01, max_val=100.0)
            if not meal:
                raise ValueError("Meal category is required.")

            if food_item_name == "OTHERS":
                name = validate_text(request.form.get("other_name") or "Other", "Custom food name", min_len=1, max_len=100)
                raw_cal = validate_non_negative_float(request.form.get("other_calories"), "Calories", max_val=10000.0)
                raw_pro = validate_non_negative_float(request.form.get("other_protein") or 0.0, "Protein", max_val=1000.0)
                raw_fat = validate_non_negative_float(request.form.get("other_fat") or 0.0, "Fat", max_val=1000.0)
                raw_sug = validate_non_negative_float(request.form.get("other_sugar") or 0.0, "Sugar", max_val=1000.0)
                calories = round(raw_cal * qty, 1)
                protein = round(raw_pro * qty, 1)
                fat = round(raw_fat * qty, 1)
                sugar = round(raw_sug * qty, 1)
            else:
                food_ref = FoodItem.query.filter_by(
                    meal_category=meal, name=food_item_name
                ).first()

                if food_ref:
                    name = food_ref.name
                    calories = round(food_ref.calories * qty, 1)
                    protein = round(food_ref.protein * qty, 1)
                    fat = round(food_ref.fat * qty, 1)
                    sugar = round(food_ref.sugar * qty, 1)
                elif meal in FOOD_DATA and food_item_name in FOOD_DATA[meal]:
                    base = FOOD_DATA[meal][food_item_name]
                    name = food_item_name
                    calories, protein, fat, sugar = [round(v * qty, 1) for v in base]
                else:
                    raise ValueError("Invalid meal or food selection.")
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("dashboard.food", date=selected_date))

        log_entry = FoodLog(
            user_id=current_user.id,
            date=selected_date,
            meal=meal,
            food=name,
            qty=qty,
            calories=calories,
            protein=protein,
            fat=fat,
            sugar=sugar
        )
        db.session.add(log_entry)
        db.session.commit()
        return redirect(url_for("dashboard.food", date=selected_date))

    food_logs = FoodLog.query.filter_by(user_id=current_user.id, date=selected_date).order_by(FoodLog.id.desc()).all()

    return render_template(
        "food.html",
        active_page="food",
        food_logs=food_logs,
        food_data=FOOD_DATA,
        selected_date=selected_date,
        max_date=get_today().isoformat(),
    )


@dashboard_bp.route("/food/delete/<int:item_id>", methods=["POST"])
@login_required
def delete_food(item_id):
    selected_date = normalize_selected_date(request.form.get("date"))
    FoodLog.query.filter_by(id=item_id, user_id=current_user.id).delete()
    db.session.commit()
    return redirect(url_for("dashboard.food", date=selected_date))


@dashboard_bp.route("/food/edit/<int:item_id>", methods=["GET", "POST"])
@login_required
def edit_food(item_id):
    food_row = FoodLog.query.filter_by(id=item_id, user_id=current_user.id).first()

    if not food_row:
        abort(404)

    if request.method == "POST":
        try:
            food_row.qty = validate_positive_float(request.form.get("qty"), "Quantity", min_val=0.01, max_val=100.0)
            food_row.calories = validate_non_negative_float(request.form.get("calories"), "Calories", max_val=10000.0)
            food_row.protein = validate_non_negative_float(request.form.get("protein"), "Protein", max_val=1000.0)
            food_row.fat = validate_non_negative_float(request.form.get("fat"), "Fat", max_val=1000.0)
            food_row.sugar = validate_non_negative_float(request.form.get("sugar"), "Sugar", max_val=1000.0)
            db.session.commit()
            return redirect(url_for("dashboard.food", date=food_row.date))
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("dashboard.edit_food", item_id=item_id))

    return render_template("edit_food.html", active_page="food", f=food_row)


@dashboard_bp.route("/sleep", methods=["GET", "POST"])
@login_required
def sleep():
    selected_date = normalize_selected_date(request.args.get("date"))

    if request.method == "POST":
        post_date = normalize_selected_date(request.form.get("date"))
        try:
            hours = validate_non_negative_float(request.form.get("hours"), "Sleep hours", max_val=24.0)
            quality = validate_int_range(request.form.get("quality"), "Sleep quality", min_val=1, max_val=5)
            notes = validate_text(request.form.get("notes"), "Notes", min_len=0, max_len=1000, allow_none=True)
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("dashboard.sleep", date=post_date))

        sleep_entry = SleepLog.query.filter_by(user_id=current_user.id, date=post_date).first()
        if not sleep_entry:
            sleep_entry = SleepLog(user_id=current_user.id, date=post_date)
            db.session.add(sleep_entry)
        
        sleep_entry.hours = hours
        sleep_entry.quality = quality
        sleep_entry.notes = notes or ""
        db.session.commit()
        return redirect(url_for("dashboard.sleep", date=post_date))

    sleep_data = SleepLog.query.filter_by(user_id=current_user.id, date=selected_date).first()

    return render_template(
        "sleep.html",
        active_page="sleep",
        sleep=sleep_data,
        selected_date=selected_date,
        max_date=get_today().isoformat(),
    )


@dashboard_bp.route("/sleep/delete", methods=["POST"])
@login_required
def delete_sleep():
    selected_date = normalize_selected_date(request.form.get("date"))
    SleepLog.query.filter_by(user_id=current_user.id, date=selected_date).delete()
    db.session.commit()
    return redirect(url_for("dashboard.sleep", date=selected_date))


@dashboard_bp.route("/wellbeing", methods=["GET", "POST"])
@login_required
def wellbeing():
    selected_date = normalize_selected_date(request.args.get("date"))

    if request.method == "POST":
        activity = (request.form.get("activity") or "").strip()
        post_date = normalize_selected_date(request.form.get("date"))
        try:
            minutes = validate_int_range(request.form.get("minutes"), "Duration (minutes)", min_val=1, max_val=1440)
            if activity == "OTHERS":
                activity = validate_text(request.form.get("other_activity") or "Other", "Activity name", min_len=1, max_len=100)
            else:
                activity = validate_text(activity, "Activity", min_len=1, max_len=100)
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("dashboard.wellbeing", date=post_date))

        log_entry = WellbeingLog(
            user_id=current_user.id,
            date=post_date,
            activity=activity,
            minutes=minutes
        )
        db.session.add(log_entry)
        db.session.commit()
        return redirect(url_for("dashboard.wellbeing", date=post_date))

    logs = WellbeingLog.query.filter_by(user_id=current_user.id, date=selected_date).order_by(WellbeingLog.id.desc()).all()

    return render_template(
        "wellbeing.html",
        active_page="wellbeing",
        wellbeing_logs=logs,
        selected_date=selected_date,
        max_date=get_today().isoformat(),
    )


@dashboard_bp.route("/wellbeing/delete/<int:item_id>", methods=["POST"])
@login_required
def delete_wellbeing(item_id):
    selected_date = normalize_selected_date(request.form.get("date"))
    WellbeingLog.query.filter_by(id=item_id, user_id=current_user.id).delete()
    db.session.commit()
    return redirect(url_for("dashboard.wellbeing", date=selected_date))


@dashboard_bp.route("/gym", methods=["GET", "POST"])
@login_required
def gym():
    selected_date = normalize_selected_date(request.args.get("date"))

    if request.method == "POST":
        post_date = normalize_selected_date(request.form.get("date", selected_date))
        intensity = request.form.get("intensity", "Medium")
        if intensity not in INTENSITY_MAP:
            intensity = "Medium"

        exercise = (request.form.get("exercise") or "").strip()
        muscle = (request.form.get("muscle") or "").strip()

        try:
            muscle = validate_text(muscle, "Muscle group", min_len=1, max_len=50)
            exercise = validate_text(exercise, "Exercise", min_len=1, max_len=100)
            is_cardio = is_cardio_exercise(exercise)

            if is_cardio:
                duration = validate_positive_float(request.form.get("duration"), "Cardio duration", min_val=1.0, max_val=1440.0)
                speed = validate_non_negative_float(request.form.get("speed") or 0.0, "Speed", max_val=100.0)
                incline = validate_non_negative_float(request.form.get("incline") or 0.0, "Incline", max_val=50.0)
                sets = reps = weight = 0
            else:
                sets = validate_int_range(request.form.get("sets"), "Sets", min_val=1, max_val=100)
                reps = validate_int_range(request.form.get("reps"), "Reps per set", min_val=1, max_val=500)
                weight = validate_non_negative_float(request.form.get("weight") or 0.0, "Weight", max_val=1000.0)
                duration = speed = incline = 0.0
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("dashboard.gym", date=post_date))

        muscle_factor = MUSCLE_FACTORS.get(muscle, 1.0)
        intensity_val = INTENSITY_MAP.get(intensity, 1.0)

        if is_cardio:
            body_weight = current_user.weight if current_user.weight else 70

            # Look up cardio metadata from the Exercise DB table first
            ex_ref = Exercise.query.filter_by(name=exercise, is_cardio=True).first()
            if ex_ref and ex_ref.cardio_meta:
                meta = json.loads(ex_ref.cardio_meta)
            else:
                from constants import CARDIO_META
                meta = CARDIO_META.get(exercise, {"met": 5.0, "baseline_speed": 6.0, "speed_factor": 0.25})

            base_met = meta["met"]
            baseline_speed = meta["baseline_speed"]
            speed_factor_val = meta["speed_factor"]
            speed_boost = max(0, speed - baseline_speed) * speed_factor_val
            incline_boost = max(0, incline) * 0.35 if exercise == "Inclined Walking" else 0
            calories = round(((base_met + speed_boost + incline_boost) * 3.5 * body_weight / 200) * duration, 1)
        else:
            eff_weight = weight if weight > 0 else 50
            calories = round((sets * reps * eff_weight * 0.04) * muscle_factor * intensity_val, 1)

        log_entry = GymLog(
            user_id=current_user.id,
            date=post_date,
            muscle=muscle,
            exercise=exercise,
            sets=sets,
            reps=reps,
            weight=weight,
            speed=speed,
            incline=incline,
            intensity=intensity,
            duration=duration,
            calories=calories
        )
        db.session.add(log_entry)
        db.session.commit()

        if not is_cardio and sets > 0:
            for s_num in range(1, sets + 1):
                ws = WorkoutSet(
                    gym_log_id=log_entry.id,
                    set_number=s_num,
                    reps=reps,
                    weight=weight,
                    completed=True,
                )
                db.session.add(ws)
            db.session.commit()

            # Personal Record detection using Epley 1RM
            if weight > 0:
                est_1rm = round(weight * (1.0 + reps / 30.0), 1)
                prior_best = (
                    db.session.query(func.max(WorkoutSet.weight * (1.0 + WorkoutSet.reps / 30.0)))
                    .join(GymLog, WorkoutSet.gym_log_id == GymLog.id)
                    .filter(GymLog.user_id == current_user.id, GymLog.exercise == exercise, GymLog.id != log_entry.id)
                    .scalar() or 0.0
                )
                if prior_best > 0 and est_1rm > prior_best:
                    flash(f"🏆 New Personal Record for {exercise}! Estimated 1RM: {est_1rm} kg (prior best: {round(prior_best, 1)} kg)")

        return redirect(url_for("dashboard.gym", date=post_date))

    logs = GymLog.query.filter_by(user_id=current_user.id, date=selected_date).order_by(GymLog.id.desc()).all()

    streak = 0
    all_dates = db.session.query(GymLog.date).filter_by(user_id=current_user.id).distinct().order_by(GymLog.date.desc()).all()
    dates = [row.date for row in all_dates]

    current_day = get_today()
    if dates and (
        dates[0] == current_day.isoformat()
        or dates[0] == (current_day - timedelta(days=1)).isoformat()
    ):
        streak = 1
        check_date = datetime.strptime(dates[0], "%Y-%m-%d").date()
        for index in range(1, len(dates)):
            if dates[index] == (check_date - timedelta(days=1)).isoformat():
                streak += 1
                check_date -= timedelta(days=1)
            else:
                break

    last_workout = GymLog.query.filter_by(user_id=current_user.id).order_by(GymLog.id.desc()).first()

    daily_challenge = get_daily_challenge(selected_date)
    challenge_completed = is_challenge_completed(current_user.id, selected_date, daily_challenge["title"])

    return render_template(
        "gym.html",
        active_page="gym",
        cardio_exercises=sorted(CARDIO_EXERCISES),
        gym_logs=logs,
        selected_date=selected_date,
        streak=streak,
        last_workout=last_workout,
        daily_challenge=daily_challenge,
        challenge_completed=challenge_completed,
        max_date=get_today().isoformat(),
    )


@dashboard_bp.route("/gym/complete-challenge", methods=["POST"])
@login_required
def complete_challenge():
    data = request.get_json(silent=True) or request.form
    selected_date = normalize_selected_date(data.get("date"))
    challenge = get_daily_challenge(selected_date)

    already_done = is_challenge_completed(current_user.id, selected_date, challenge["title"])
    if already_done:
        return jsonify({
            "success": True,
            "already_completed": True,
            "message": "Challenge already completed for today!"
        }), 200

    elapsed_seconds = data.get("elapsed_seconds")
    duration_mins = challenge["duration"]
    if elapsed_seconds:
        try:
            duration_mins = max(1.0, round(float(elapsed_seconds) / 60.0, 1))
        except (ValueError, TypeError):
            duration_mins = challenge["duration"]

    exercise_name = f"Daily Challenge: {challenge['title']}"
    log_entry = GymLog(
        user_id=current_user.id,
        date=selected_date,
        muscle=challenge["muscle"],
        exercise=exercise_name,
        sets=1,
        reps=1,
        weight=0.0,
        speed=0.0,
        incline=0.0,
        duration=duration_mins,
        intensity="High",
        calories=challenge["calories"]
    )
    db.session.add(log_entry)
    db.session.commit()

    return jsonify({
        "success": True,
        "already_completed": False,
        "calories": challenge["calories"],
        "duration": duration_mins,
        "title": challenge["title"],
        "message": f"🎉 {challenge['title']} completed! +{int(challenge['calories'])} kcal burned."
    }), 200


@dashboard_bp.route("/gym/delete/<int:item_id>", methods=["POST"])
@login_required
def delete_gym(item_id):
    selected_date = normalize_selected_date(request.form.get("date"))
    item = GymLog.query.filter_by(id=item_id, user_id=current_user.id).first()
    if item:
        db.session.delete(item)
        db.session.commit()
    return redirect(url_for("dashboard.gym", date=selected_date))


# ───────────────────────── Lookup API ──────────────────────────

@dashboard_bp.route("/api/food-items")
@login_required
def api_food_items():
    """Return food items for a given meal category.
    Query param: ?category=Breakfast
    """
    category = request.args.get("category", "").strip()
    if not category:
        # Return all categories grouped
        result = {}
        for item in FoodItem.query.order_by(FoodItem.meal_category, FoodItem.name).all():
            result.setdefault(item.meal_category, []).append(item.to_dict())
        return jsonify(result)

    items = FoodItem.query.filter_by(meal_category=category).order_by(FoodItem.name).all()
    return jsonify([i.to_dict() for i in items])


@dashboard_bp.route("/api/exercises")
@login_required
def api_exercises():
    """Return exercises for a given muscle group.
    Query param: ?muscle=Chest
    Returns all exercises grouped by muscle_group if no param supplied.
    """
    muscle = request.args.get("muscle", "").strip()
    if not muscle:
        result = {}
        for ex in Exercise.query.order_by(Exercise.muscle_group, Exercise.name).all():
            result.setdefault(ex.muscle_group, []).append(ex.to_dict())
        return jsonify(result)

    exercises = Exercise.query.filter_by(muscle_group=muscle).order_by(Exercise.name).all()
    return jsonify([e.to_dict() for e in exercises])


# ───────────────────────── CSV Export ──────────────────────────

@dashboard_bp.route("/export/csv")
@login_required
def export_csv():
    """Download all logs for the current user as a CSV file.

    Optional query params:
        ?from=YYYY-MM-DD  (default: 30 days ago)
        ?to=YYYY-MM-DD    (default: today)
    """
    import csv
    import io
    from datetime import timedelta
    from flask import Response

    today = get_today()
    try:
        date_from = date.fromisoformat(request.args.get("from", (today - timedelta(days=30)).isoformat()))
        date_to   = date.fromisoformat(request.args.get("to",   today.isoformat()))
    except ValueError:
        date_from = today - timedelta(days=30)
        date_to   = today

    # Clamp so from <= to
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    date_from_s = date_from.isoformat()
    date_to_s   = date_to.isoformat()

    output = io.StringIO()
    writer = csv.writer(output)

    # ── Food log ──────────────────────────────────────────────
    writer.writerow(["=== Food Log ==="])
    writer.writerow(["Date", "Meal", "Food", "Qty", "Calories", "Protein (g)", "Fat (g)", "Sugar (g)"])
    food_rows = (
        FoodLog.query
        .filter(FoodLog.user_id == current_user.id,
                FoodLog.date >= date_from_s,
                FoodLog.date <= date_to_s)
        .order_by(FoodLog.date, FoodLog.id)
        .all()
    )
    for r in food_rows:
        writer.writerow([r.date, r.meal, r.food, r.qty,
                         round(r.calories or 0, 2),
                         round(r.protein  or 0, 2),
                         round(r.fat      or 0, 2),
                         round(r.sugar    or 0, 2)])

    writer.writerow([])

    # ── Sleep log ─────────────────────────────────────────────
    writer.writerow(["=== Sleep Log ==="])
    writer.writerow(["Date", "Hours", "Quality (1-5)", "Notes"])
    sleep_rows = (
        SleepLog.query
        .filter(SleepLog.user_id == current_user.id,
                SleepLog.date >= date_from_s,
                SleepLog.date <= date_to_s)
        .order_by(SleepLog.date)
        .all()
    )
    for r in sleep_rows:
        writer.writerow([r.date, r.hours, r.quality, r.notes or ""])

    writer.writerow([])

    # ── Gym log ───────────────────────────────────────────────
    writer.writerow(["=== Gym Log ==="])
    writer.writerow(["Date", "Muscle", "Exercise", "Sets", "Reps", "Weight (kg)",
                     "Speed (km/h)", "Incline (%)", "Intensity", "Duration (min)", "Calories Burned"])
    gym_rows = (
        GymLog.query
        .filter(GymLog.user_id == current_user.id,
                GymLog.date >= date_from_s,
                GymLog.date <= date_to_s)
        .order_by(GymLog.date, GymLog.id)
        .all()
    )
    for r in gym_rows:
        writer.writerow([r.date, r.muscle, r.exercise,
                         r.sets or 0, r.reps or 0,
                         round(r.weight   or 0, 2),
                         round(r.speed    or 0, 2),
                         round(r.incline  or 0, 2),
                         r.intensity or "",
                         round(r.duration or 0, 2),
                         round(r.calories or 0, 2)])

    writer.writerow([])

    # ── Wellbeing log ─────────────────────────────────────────
    writer.writerow(["=== Wellbeing Log ==="])
    writer.writerow(["Date", "Activity", "Duration (min)"])
    wb_rows = (
        WellbeingLog.query
        .filter(WellbeingLog.user_id == current_user.id,
                WellbeingLog.date >= date_from_s,
                WellbeingLog.date <= date_to_s)
        .order_by(WellbeingLog.date, WellbeingLog.id)
        .all()
    )
    for r in wb_rows:
        writer.writerow([r.date, r.activity, r.minutes])

    output.seek(0)
    filename = f"vitallog_{current_user.email}_{date_from_s}_to_{date_to_s}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )



@dashboard_bp.route("/report")
@login_required
def report():
    selected_date = normalize_selected_date(request.args.get("date"))
    week = get_week_dates(selected_date)

    meals = db.session.query(
        FoodLog.meal,
        func.sum(FoodLog.calories).label('cal'),
        func.sum(FoodLog.protein).label('protein'),
        func.sum(FoodLog.fat).label('fat'),
        func.sum(FoodLog.sugar).label('sugar')
    ).filter(FoodLog.user_id == current_user.id, FoodLog.date == selected_date).group_by(FoodLog.meal).all()

    # ── Optimized Weekly Aggregations (Single Grouped Queries - No N+1) ──
    food_by_date = dict(
        db.session.query(FoodLog.date, func.coalesce(func.sum(FoodLog.calories), 0))
        .filter(FoodLog.user_id == current_user.id, FoodLog.date.in_(week))
        .group_by(FoodLog.date).all()
    )
    sleep_by_date = {
        row.date: row.hours
        for row in SleepLog.query.filter(SleepLog.user_id == current_user.id, SleepLog.date.in_(week)).all()
    }
    wb_by_date = dict(
        db.session.query(WellbeingLog.date, func.coalesce(func.sum(WellbeingLog.minutes), 0))
        .filter(WellbeingLog.user_id == current_user.id, WellbeingLog.date.in_(week))
        .group_by(WellbeingLog.date).all()
    )
    gym_by_date = dict(
        db.session.query(GymLog.date, func.coalesce(func.sum(GymLog.calories), 0))
        .filter(GymLog.user_id == current_user.id, GymLog.date.in_(week))
        .group_by(GymLog.date).all()
    )

    weekly_cal = [round(float(food_by_date.get(d, 0) or 0), 1) for d in week]
    weekly_sleep = [round(float(sleep_by_date.get(d, 0) or 0), 1) for d in week]
    weekly_wellbeing = [int(wb_by_date.get(d, 0) or 0) for d in week]
    weekly_gym = [round(float(gym_by_date.get(d, 0) or 0), 1) for d in week]

    weight_by_date = {
        row.date: row.weight
        for row in WeightLog.query.filter(WeightLog.user_id == current_user.id, WeightLog.date.in_(week)).all()
    }
    weekly_weight = [weight_by_date.get(d) for d in week]

    gym_logs = GymLog.query.filter_by(user_id=current_user.id, date=selected_date).all()
    gym_total = db.session.query(func.coalesce(func.sum(GymLog.calories), 0)).filter(GymLog.user_id == current_user.id, GymLog.date == selected_date).scalar() or 0

    return render_template(
        "report.html",
        active_page="report",
        meals=meals,
        gym_logs=gym_logs,
        gym_total=gym_total,
        selected_date=selected_date,
        week=week,
        weekly_cal=weekly_cal,
        weekly_sleep=weekly_sleep,
        weekly_wellbeing=weekly_wellbeing,
        weekly_gym=weekly_gym,
        weekly_weight=weekly_weight,
        max_date=get_today().isoformat(),
    )

@dashboard_bp.route("/admin/users")
@login_required
def admin_users():
    if not is_admin_user():
        abort(403)

    users = User.query.order_by(User.id.desc()).all()
    total_users = len(users)
    active_users = sum(1 for user in users if int(user.is_active or 0) == 1)

    return render_template(
        "admin_users.html",
        active_page="admin_users",
        users=users,
        total_users=total_users,
        active_users=active_users,
        inactive_users=total_users - active_users,
    )


@dashboard_bp.route("/chat/history", methods=["GET"])
@login_required
def chat_history():
    # Fetch the 30 most recent messages, ordered descending so we get the latest ones
    recent_msgs = ChatMessage.query.filter_by(user_id=current_user.id)\
        .order_by(ChatMessage.created_at.desc())\
        .limit(30)\
        .all()
    
    # Reverse so they are returned in chronological order
    recent_msgs.reverse()
    
    return jsonify({
        "messages": [
            {"role": msg.role, "content": msg.content}
            for msg in recent_msgs
        ]
    })


def build_coach_context(user_id: int) -> dict:
    """Assemble structured, multi-domain user context for AI fitness coaching."""
    user = db.session.get(User, user_id)
    if not user:
        return {}

    today = get_today()
    today_str = today.isoformat()
    seven_days_ago = (today - timedelta(days=6)).isoformat()
    fourteen_days_ago = (today - timedelta(days=13)).isoformat()

    # Preferences
    pref = get_or_create_user_preferences(user_id)

    # 7-day nutrition averages
    nutrition_7d = db.session.query(
        func.coalesce(func.sum(FoodLog.calories), 0).label("cals"),
        func.coalesce(func.sum(FoodLog.protein), 0).label("protein"),
        func.count(func.distinct(FoodLog.date)).label("logged_days")
    ).filter(FoodLog.user_id == user_id, FoodLog.date >= seven_days_ago, FoodLog.date <= today_str).first()

    logged_days = int(nutrition_7d.logged_days or 0) if nutrition_7d else 0
    days_div = max(1, logged_days)
    avg_calories_7d = round(float(nutrition_7d.cals) / days_div, 1) if (nutrition_7d and logged_days > 0) else 0.0
    avg_protein_7d = round(float(nutrition_7d.protein) / days_div, 1) if (nutrition_7d and logged_days > 0) else 0.0

    today_food = db.session.query(
        func.coalesce(func.sum(FoodLog.calories), 0).label("cals"),
        func.coalesce(func.sum(FoodLog.protein), 0).label("protein"),
    ).filter(FoodLog.user_id == user_id, FoodLog.date == today_str).first()
    today_cals = round(float(today_food.cals), 1) if today_food else 0.0
    today_protein = round(float(today_food.protein), 1) if today_food else 0.0

    # 14-day weight trend
    weight_logs = WeightLog.query.filter(
        WeightLog.user_id == user_id,
        WeightLog.date >= fourteen_days_ago,
        WeightLog.date <= today_str
    ).order_by(WeightLog.date.asc()).all()

    starting_weight = weight_logs[0].weight if weight_logs else user.weight
    current_weight = weight_logs[-1].weight if weight_logs else user.weight
    weight_delta = round(current_weight - starting_weight, 2) if (current_weight and starting_weight) else 0.0

    # Recent workouts & top PRs
    recent_workouts = (
        GymLog.query.filter(GymLog.user_id == user_id, GymLog.date >= seven_days_ago)
        .order_by(GymLog.date.desc())
        .limit(10)
        .all()
    )
    recent_exercises = list(dict.fromkeys(w.exercise for w in recent_workouts))
    today_gym = [w for w in recent_workouts if w.date == today_str]
    today_gym_calories = round(sum(w.calories for w in today_gym), 1)

    pr_rows = (
        db.session.query(
            GymLog.exercise,
            func.max(WorkoutSet.weight * (1.0 + WorkoutSet.reps / 30.0)).label("max_1rm")
        )
        .join(WorkoutSet, WorkoutSet.gym_log_id == GymLog.id)
        .filter(GymLog.user_id == user_id, WorkoutSet.weight > 0)
        .group_by(GymLog.exercise)
        .order_by(func.max(WorkoutSet.weight * (1.0 + WorkoutSet.reps / 30.0)).desc())
        .limit(3)
        .all()
    )
    top_prs = [{row.exercise: round(float(row.max_1rm), 1)} for row in pr_rows]

    # Sleep
    sleep_rows = SleepLog.query.filter(
        SleepLog.user_id == user_id,
        SleepLog.date >= seven_days_ago,
        SleepLog.date <= today_str
    ).all()
    avg_sleep_7d = round(sum(s.hours for s in sleep_rows) / len(sleep_rows), 1) if sleep_rows else None
    today_sleep_row = next((s for s in sleep_rows if s.date == today_str), None)
    today_sleep = today_sleep_row.hours if today_sleep_row else None

    # TDEE
    activity_multipliers = {
        "sedentary": 1.2,
        "light": 1.375,
        "moderate": 1.55,
        "active": 1.725,
    }
    act_factor = activity_multipliers.get(pref.activity_level, 1.375)
    tdee = calculate_tdee(user.weight, user.height, user.age, pref.gender, act_factor) if (user.weight and user.height and user.age) else None

    return {
        "user_id": user_id,
        "name": user.name or user.email,
        "age": user.age,
        "height_cm": user.height,
        "weight_kg": current_weight,
        "starting_weight_14d": starting_weight,
        "weight_delta_14d": weight_delta,
        "goals": {
            "calories": user.goal_calories or 1500,
            "protein": user.goal_protein or 100,
            "tdee": tdee,
        },
        "preferences": {
            "fitness_goal": pref.fitness_goal,
            "diet_type": pref.diet_type,
            "experience_level": pref.experience_level,
            "equipment_access": pref.equipment_access,
            "activity_level": pref.activity_level,
            "target_sleep_hours": pref.target_sleep_hours,
            "injury_notes": pref.injury_notes,
        },
        "averages_7d": {
            "avg_calories": avg_calories_7d,
            "avg_protein": avg_protein_7d,
            "avg_sleep_hours": avg_sleep_7d,
            "logged_days": logged_days,
        },
        "recent_exercises": recent_exercises,
        "top_prs": top_prs,
        "today": {
            "date": today_str,
            "food_calories": today_cals,
            "protein_g": today_protein,
            "estimated_gym_calories": today_gym_calories,
            "sleep_hours": today_sleep,
        }
    }


def format_coach_system_prompt(ctx: dict) -> str:
    """Format structured user context and safety guidelines into an LLM system prompt."""
    name = ctx.get("name", "User")
    age = ctx.get("age") or "Not set"
    height = f"{ctx.get('height_cm')} cm" if ctx.get("height_cm") else "Not set"
    weight = f"{ctx.get('weight_kg')} kg" if ctx.get("weight_kg") else "Not set"

    goals = ctx.get("goals", {})
    prefs = ctx.get("preferences", {})
    avg7 = ctx.get("averages_7d", {})
    today = ctx.get("today", {})

    prs_str = ", ".join(f"{list(pr.keys())[0]}: {list(pr.values())[0]}kg est. 1RM" for pr in ctx.get("top_prs", [])) or "None recorded yet"
    exercises_str = ", ".join(ctx.get("recent_exercises", [])) or "No recent strength workouts"

    injuries = prefs.get("injury_notes") or "None reported"

    prompt = f"""You are VitalLog Coach, an intelligent, empathetic, and evidence-based personal fitness and wellness assistant.

### User Profile & Preferences:
- Athlete: {name} (Age: {age}, Height: {height}, Current Weight: {weight})
- Primary Goal: {prefs.get('fitness_goal', 'maintenance').replace('_', ' ').title()}
- Diet Type: {prefs.get('diet_type', 'standard').replace('_', ' ').title()}
- Training Experience: {prefs.get('experience_level', 'intermediate').title()}
- Equipment Access: {prefs.get('equipment_access', 'full_gym').replace('_', ' ').title()}
- Sleep Target: {prefs.get('target_sleep_hours', 8.0)} hrs/night
- Injuries / Limitations: {injuries}

### Recent Trends & Baselines:
- Calorie Target: {goals.get('calories')} kcal/day | Estimated TDEE: {goals.get('tdee') or 'Requires age/height/weight'} kcal
- 7-Day Average Intake: {avg7.get('avg_calories')} kcal ({avg7.get('avg_protein')}g protein across {avg7.get('logged_days')} logged days)
- 14-Day Weight Trend: {ctx.get('weight_delta_14d', 0.0):+0.2f} kg change (from {ctx.get('starting_weight_14d')}kg to {ctx.get('weight_kg')}kg)
- 7-Day Average Sleep: {avg7.get('avg_sleep_hours') or 'No logs'} hrs
- Recent Exercises: {exercises_str}
- Top Personal Records: {prs_str}

### Today's Snapshot ({today.get('date')}):
- Nutrition: {today.get('food_calories', 0)} kcal consumed ({today.get('protein_g', 0)}g protein)
- Activity: {today.get('estimated_gym_calories', 0)} kcal estimated burn
- Sleep: {today.get('sleep_hours') or 'Not logged yet'} hrs

### Coaching Persona & Guardrails:
1. Tone: Warm, constructive, grounded, and non-judgmental. Never use guilt, shame, or scolding for missed logs, higher-calorie days, or rest days.
2. Estimates vs Measurements: Always treat exercise calorie burn as an estimate. Note that day-to-day weight fluctuations reflect hydration and glycogen shifts rather than pure tissue change.
3. Constraint Alignment: Respect diet type (do not suggest meat/poultry to vegetarians or vegans), respect available equipment (do not prescribe barbells for home bodyweight), and NEVER recommend movements that stress noted injuries ({injuries}).
4. Safety & Medical Boundaries: You are a fitness coach, not a doctor. Never provide medical diagnoses or prescribe medications. Refer the user to a physician for medical concerns.
5. Read-Only Assurance: You are an advisory AI. You cannot and do not alter logs or profile settings autonomously.
6. Conciseness: Keep responses focused, practical, and conversational (typically 2-4 sentences, or short bullet points when answering specific workout/nutrition queries)."""

    return prompt


@dashboard_bp.route("/chat", methods=["POST"])
@login_required
def chat():
    # Rate limit: max 20 messages per minute per user
    if not chat_rate_limiter.is_allowed(f"user_{current_user.id}"):
        return jsonify({
            "reply": "You're sending messages a bit too fast. Please take a breath and try again in a moment!"
        }), 429

    data = request.json or {}
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"reply": "Please enter a message."}), 400

    client = get_groq_client()
    if not client:
        return jsonify({
            "reply": "AI Chatbot is not configured. Please set the GROQ_API_KEY environment variable."
        }), 503

    # 1. Save user message to database
    user_msg_db = ChatMessage(user_id=current_user.id, role="user", content=user_message)
    db.session.add(user_msg_db)
    db.session.commit()

    # 2. Retrieve recent conversation history for context (last 15 messages)
    history = ChatMessage.query.filter_by(user_id=current_user.id)\
        .order_by(ChatMessage.created_at.desc())\
        .limit(15)\
        .all()
    history.reverse()

    # 3. Retrieve stats and build structured context
    coach_ctx = build_coach_context(current_user.id)
    system_prompt = format_coach_system_prompt(coach_ctx)

    # 4. Format messages for Groq Completions API
    api_messages = [
        {"role": "system", "content": system_prompt}
    ]
    for msg in history:
        api_messages.append({"role": msg.role, "content": msg.content})

    preferred_model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
    candidate_models = [preferred_model]
    for fallback in ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"]:
        if fallback not in candidate_models:
            candidate_models.append(fallback)

    try:
        chat_completion = None
        last_api_err = None
        for model in candidate_models:
            try:
                chat_completion = client.chat.completions.create(
                    messages=api_messages,
                    model=model,
                    temperature=0.7,
                    max_tokens=256,
                )
                if chat_completion and chat_completion.choices:
                    break
            except Exception as model_err:
                last_api_err = model_err
                print(f"Chatbot model '{model}' failed: {model_err}. Trying fallback...")

        if not chat_completion or not chat_completion.choices:
            raise last_api_err or Exception("All AI model candidates failed.")

        reply = chat_completion.choices[0].message.content

        # 5. Save assistant reply to database
        assistant_msg_db = ChatMessage(user_id=current_user.id, role="assistant", content=reply)
        db.session.add(assistant_msg_db)
        db.session.commit()

        return jsonify({"reply": reply})
    except Exception as e:
        print(f"Chatbot Error: {e}")
        return jsonify({"reply": "I'm sorry, I'm having trouble connecting. Try again in a moment!"}), 500


# ===========================================================================
# Dated Body-Weight History (Stage 2.4)
# ===========================================================================

@dashboard_bp.route("/weight", methods=["GET", "POST"])
@login_required
def weight():
    selected_date = normalize_selected_date(request.args.get("date"))

    if request.method == "POST":
        post_date = normalize_selected_date(request.form.get("date") or selected_date)
        raw_w = request.form.get("weight")
        notes = request.form.get("notes")
        try:
            w_val = validate_positive_float(raw_w, "Weight", min_val=20.0, max_val=500.0)
            valid_notes = validate_text(notes, "Notes", min_len=0, max_len=500, allow_none=True)
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("dashboard.weight", date=post_date))

        record_weight_log(current_user.id, post_date, w_val, valid_notes)
        flash("Weight entry saved successfully.")
        return redirect(url_for("dashboard.weight", date=post_date))

    logs = WeightLog.query.filter_by(user_id=current_user.id).order_by(WeightLog.date.desc()).all()
    current_entry = WeightLog.query.filter_by(user_id=current_user.id, date=selected_date).first()

    delta = None
    if len(logs) >= 2:
        delta = round(logs[0].weight - logs[1].weight, 2)

    return render_template(
        "weight.html",
        active_page="weight",
        weight_logs=logs,
        current_entry=current_entry,
        recent_delta=delta,
        selected_date=selected_date,
        max_date=get_today().isoformat(),
    )


@dashboard_bp.route("/weight/delete/<int:item_id>", methods=["POST"])
@login_required
def delete_weight(item_id):
    entry = WeightLog.query.filter_by(id=item_id, user_id=current_user.id).first()
    if entry:
        db.session.delete(entry)
        latest = WeightLog.query.filter_by(user_id=current_user.id).order_by(WeightLog.date.desc()).first()
        current_user.weight = latest.weight if latest else None
        db.session.commit()
        flash("Weight entry removed.")
    return redirect(url_for("dashboard.weight"))


@dashboard_bp.route("/api/weight-history", methods=["GET"])
@login_required
def api_weight_history():
    logs = WeightLog.query.filter_by(user_id=current_user.id).order_by(WeightLog.date.asc()).all()
    readings = [{"date": log.date, "weight": log.weight} for log in logs]
    moving_avg = []
    window = []
    for log in logs:
        window.append(log.weight)
        if len(window) > 7:
            window.pop(0)
        moving_avg.append(round(sum(window) / len(window), 2))

    return jsonify({
        "readings": readings,
        "moving_average": moving_avg,
        "count": len(readings)
    })


# ===========================================================================
# Faster Nutrition Logging: Favorites & Saved Meals (Stage 3)
# ===========================================================================

@dashboard_bp.route("/api/food/favorite", methods=["POST"])
@login_required
def toggle_food_favorite():
    data = request.json or {}
    meal_category = (data.get("meal_category") or "").strip()
    name = (data.get("name") or "").strip()
    if not meal_category or not name:
        return jsonify({"error": "meal_category and name are required"}), 400

    fav = FoodFavorite.query.filter_by(user_id=current_user.id, meal_category=meal_category, name=name).first()
    if fav:
        db.session.delete(fav)
        db.session.commit()
        return jsonify({"is_favorite": False, "message": "Removed from favorites."})
    else:
        fav = FoodFavorite(user_id=current_user.id, meal_category=meal_category, name=name)
        db.session.add(fav)
        db.session.commit()
        return jsonify({"is_favorite": True, "message": "Saved to favorites!"})


@dashboard_bp.route("/api/food/recents", methods=["GET"])
@login_required
def get_food_recents():
    cutoff = (get_today() - timedelta(days=14)).isoformat()
    recent_rows = db.session.query(FoodLog.meal, FoodLog.food, func.count(FoodLog.id).label('cnt'))\
        .filter(FoodLog.user_id == current_user.id, FoodLog.date >= cutoff)\
        .group_by(FoodLog.meal, FoodLog.food)\
        .order_by(func.count(FoodLog.id).desc())\
        .limit(10).all()
    recents = [{"meal": r.meal, "name": r.food} for r in recent_rows]

    favorites = FoodFavorite.query.filter_by(user_id=current_user.id).all()
    fav_list = [{"meal": f.meal_category, "name": f.name} for f in favorites]

    return jsonify({"recents": recents, "favorites": fav_list})


@dashboard_bp.route("/saved-meals", methods=["GET"])
@login_required
def saved_meals_list():
    meals = SavedMeal.query.filter_by(user_id=current_user.id).order_by(SavedMeal.created_at.desc()).all()
    return jsonify({"saved_meals": [m.to_dict() for m in meals]})


@dashboard_bp.route("/saved-meals/create", methods=["POST"])
@login_required
def create_saved_meal():
    data = request.json or {}
    name = (data.get("name") or "").strip()
    meal_category = (data.get("meal_category") or "Lunch").strip()
    items = data.get("items", [])
    if not name:
        return jsonify({"error": "Meal name is required"}), 400
    if not items:
        return jsonify({"error": "At least one food item is required"}), 400

    saved_meal = SavedMeal(user_id=current_user.id, name=name, meal_category=meal_category)
    db.session.add(saved_meal)
    db.session.flush()

    for itm in items:
        food_name = itm.get("food", "").strip()
        qty = float(itm.get("qty", 1.0))
        cal = float(itm.get("calories", 0.0))
        pro = float(itm.get("protein", 0.0))
        fat = float(itm.get("fat", 0.0))
        sug = float(itm.get("sugar", 0.0))
        meal_item = SavedMealItem(
            saved_meal_id=saved_meal.id,
            food=food_name,
            qty=qty,
            calories=cal,
            protein=pro,
            fat=fat,
            sugar=sug
        )
        db.session.add(meal_item)

    db.session.commit()
    return jsonify({"success": True, "meal": saved_meal.to_dict()})


@dashboard_bp.route("/saved-meals/log/<int:meal_id>", methods=["POST"])
@login_required
def log_saved_meal(meal_id):
    meal = SavedMeal.query.filter_by(id=meal_id, user_id=current_user.id).first()
    if not meal:
        return jsonify({"error": "Saved meal not found"}), 404

    data = request.json or {}
    date_str = normalize_selected_date(data.get("date") or get_today().isoformat())

    for item in meal.items:
        log = FoodLog(
            user_id=current_user.id,
            date=date_str,
            meal=meal.meal_category,
            food=item.food,
            qty=item.qty,
            calories=item.calories,
            protein=item.protein,
            fat=item.fat,
            sugar=item.sugar
        )
        db.session.add(log)
    db.session.commit()
    return jsonify({"success": True, "message": f"Logged '{meal.name}' for {date_str}!"})


@dashboard_bp.route("/saved-meals/delete/<int:meal_id>", methods=["POST"])
@login_required
def delete_saved_meal(meal_id):
    meal = SavedMeal.query.filter_by(id=meal_id, user_id=current_user.id).first()
    if meal:
        db.session.delete(meal)
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"error": "Meal not found"}), 404


# ===========================================================================
# Set-by-Set Strength Training & Progression Analytics (Stage 4)
# ===========================================================================

@dashboard_bp.route("/gym/sets/save", methods=["POST"])
@login_required
def save_gym_sets():
    data = request.json or {}
    post_date = normalize_selected_date(data.get("date") or get_today().isoformat())
    muscle = (data.get("muscle") or "").strip()
    exercise = (data.get("exercise") or "").strip()
    intensity = data.get("intensity", "Medium")
    if intensity not in INTENSITY_MAP:
        intensity = "Medium"
    sets_data = data.get("sets", [])

    if not exercise or not muscle or not sets_data:
        return jsonify({"error": "Exercise, muscle, and set records are required"}), 400

    muscle_factor = MUSCLE_FACTORS.get(muscle, 1.0)
    intensity_val = INTENSITY_MAP.get(intensity, 1.0)

    total_calories = 0.0
    max_weight = 0.0
    best_est_1rm = 0.0

    try:
        gym_log = GymLog(
            user_id=current_user.id,
            date=post_date,
            muscle=muscle,
            exercise=exercise,
            sets=len(sets_data),
            reps=sum(int(s.get("reps", 0)) for s in sets_data),
            weight=max(float(s.get("weight", 0.0)) for s in sets_data),
            speed=0.0,
            incline=0.0,
            intensity=intensity,
            duration=0.0,
            calories=0.0
        )
        db.session.add(gym_log)
        db.session.flush()

        for idx, s in enumerate(sets_data, start=1):
            reps = validate_int_range(s.get("reps"), "Reps", min_val=1, max_val=500)
            weight = validate_non_negative_float(s.get("weight", 0.0), "Weight", max_val=1000.0)
            rpe = parse_optional_float(str(s.get("rpe", "")))
            eff_weight = weight if weight > 0 else 50.0
            set_cal = (1 * reps * eff_weight * 0.04) * muscle_factor * intensity_val
            total_calories += set_cal

            est_1rm = round(weight * (1.0 + reps / 30.0), 1) if weight > 0 else 0.0
            if est_1rm > best_est_1rm:
                best_est_1rm = est_1rm
            if weight > max_weight:
                max_weight = weight

            ws = WorkoutSet(
                gym_log_id=gym_log.id,
                set_number=idx,
                reps=reps,
                weight=weight,
                completed=True,
                rpe=rpe,
            )
            db.session.add(ws)

        gym_log.calories = round(total_calories, 1)
        db.session.commit()

        # Check for PR: compare with prior workouts
        prior_best = (
            db.session.query(func.max(WorkoutSet.weight * (1.0 + WorkoutSet.reps / 30.0)))
            .join(GymLog, WorkoutSet.gym_log_id == GymLog.id)
            .filter(GymLog.user_id == current_user.id, GymLog.exercise == exercise, GymLog.id != gym_log.id)
            .scalar() or 0.0
        )
        is_pr = bool((best_est_1rm > prior_best) and (prior_best > 0.0))

        return jsonify({
            "success": True,
            "gym_log_id": gym_log.id,
            "calories": gym_log.calories,
            "estimated_1rm": best_est_1rm,
            "is_pr": is_pr,
        })
    except ValueError as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@dashboard_bp.route("/api/exercise-history", methods=["GET"])
@login_required
def exercise_history():
    exercise_name = (request.args.get("exercise") or "").strip()
    if not exercise_name:
        return jsonify({"error": "Exercise name required"}), 400

    logs = (
        GymLog.query.filter_by(user_id=current_user.id, exercise=exercise_name)
        .order_by(GymLog.date.asc(), GymLog.id.asc())
        .all()
    )
    history = []
    for l in logs:
        sets_data = [s.to_dict() for s in l.sets_detail]
        history.append({
            "id": l.id,
            "date": l.date,
            "sets_count": l.sets,
            "reps": l.reps,
            "weight": l.weight,
            "calories": l.calories,
            "sets": sets_data,
        })

    return jsonify({"exercise": exercise_name, "history": history})
