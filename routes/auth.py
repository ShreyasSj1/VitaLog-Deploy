from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from firebase_admin import auth as firebase_auth

from extensions import db
from models import (
    get_user_by_email, default_role_for_email, claim_legacy_rows, User,
    get_or_create_user_preferences
)
from utils import (
    parse_optional_int, parse_optional_float, auth_rate_limiter,
    validate_int_range, validate_positive_float, validate_non_negative_float,
    validate_text
)

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/api/auth/firebase", methods=["POST"])
def auth_firebase():
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1").split(",")[0].strip()
    if not auth_rate_limiter.is_allowed(client_ip):
        return jsonify({"error": "Too many authentication attempts. Please wait a moment before trying again."}), 429

    data = request.json or {}
    id_token = data.get("idToken")
    name = data.get("name", "")
    
    if not id_token:
        return jsonify({"error": "No token provided"}), 400
        
    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        email = decoded_token.get('email', '').strip().lower()
        email_verified = bool(decoded_token.get('email_verified', False))
    except Exception as e:
        print(f"Firebase token verification failed: {e}")
        return jsonify({"error": "Invalid token"}), 401

    if not email:
        return jsonify({"error": "Email is required"}), 400
        
    try:
        # Look up user or create them
        user = get_user_by_email(email)
        if user:
            # Prevent account takeover: if the account already exists, the token must be verified
            # (e.g., Google OAuth or email-verified password account)
            if not email_verified:
                return jsonify({
                    "error": "This email is associated with an existing account. Please verify your email before signing in."
                }), 403
        else:
            role = default_role_for_email(email)
            user = User(
                email=email,
                password_hash='firebase_managed',
                name=name or email,
                role=role,
                is_active=1
            )
            db.session.add(user)
            db.session.commit()
            claim_legacy_rows(user.id)
            
        if not user.is_active:
            return jsonify({"error": "Account inactive"}), 403
            
        login_user(user)
        return jsonify({"success": True})
    except Exception as e:
        print(f"Database error during auth: {e}")
        return jsonify({"error": "Database connection error"}), 500



@auth_bp.route("/login", methods=["GET"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    return render_template("login.html")


@auth_bp.route("/register", methods=["GET"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    return render_template("register.html")


@auth_bp.route("/logout", methods=["POST", "GET"])
@login_required
def logout():
    logout_user()
    flash("You're signed out for now. Let's get you back on track.")
    return redirect(url_for("auth.login"))


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        name = request.form.get("name", "").strip() or current_user.email
        try:
            raw_age = request.form.get("age", "").strip()
            age = validate_int_range(raw_age, "Age", 5, 120, allow_none=True) if raw_age else None

            raw_h = request.form.get("height", "").strip()
            height = validate_positive_float(raw_h, "Height", min_val=30.0, max_val=300.0) if raw_h else None

            raw_w = request.form.get("weight", "").strip()
            weight = validate_positive_float(raw_w, "Weight", min_val=20.0, max_val=500.0) if raw_w else None

            raw_gc = request.form.get("goal_calories", "").strip()
            goal_calories = validate_positive_float(raw_gc, "Calorie goal", min_val=500.0, max_val=15000.0) if raw_gc else None

            raw_gp = request.form.get("goal_protein", "").strip()
            goal_protein = validate_non_negative_float(raw_gp, "Protein goal", max_val=1000.0, allow_none=True) if raw_gp else None

            raw_gf = request.form.get("goal_fat", "").strip()
            goal_fat = validate_non_negative_float(raw_gf, "Fat limit", max_val=1000.0, allow_none=True) if raw_gf else None

            raw_gs = request.form.get("goal_sugar", "").strip()
            goal_sugar = validate_non_negative_float(raw_gs, "Sugar limit", max_val=1000.0, allow_none=True) if raw_gs else None
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("auth.profile"))

        # Update coaching preferences
        pref = get_or_create_user_preferences(current_user.id)
        raw_goal = request.form.get("fitness_goal", "").strip()
        if raw_goal in ("fat_loss", "muscle_gain", "strength", "maintenance"):
            pref.fitness_goal = raw_goal
        raw_diet = request.form.get("diet_type", "").strip()
        if raw_diet in ("standard", "vegetarian", "non_vegetarian", "vegan", "eggetarian"):
            pref.diet_type = raw_diet
        raw_exp = request.form.get("experience_level", "").strip()
        if raw_exp in ("beginner", "intermediate", "advanced"):
            pref.experience_level = raw_exp
        raw_equip = request.form.get("equipment_access", "").strip()
        if raw_equip in ("full_gym", "dumbbells_only", "home_bodyweight"):
            pref.equipment_access = raw_equip
        raw_act = request.form.get("activity_level", "").strip()
        if raw_act in ("sedentary", "light", "moderate", "active"):
            pref.activity_level = raw_act
        raw_gen = request.form.get("gender", "").strip()
        if raw_gen in ("male", "female", "unspecified"):
            pref.gender = raw_gen
        raw_sleep_t = request.form.get("target_sleep_hours", "").strip()
        if raw_sleep_t:
            try:
                pref.target_sleep_hours = validate_positive_float(raw_sleep_t, "Target sleep", min_val=4.0, max_val=16.0)
            except ValueError:
                pass
        pref.injury_notes = validate_text(request.form.get("injury_notes"), "Injuries", min_len=0, max_len=1000, allow_none=True)

        current_user.name          = name
        current_user.age           = age
        current_user.height        = height
        current_user.weight        = weight
        current_user.goal_calories = goal_calories
        current_user.goal_protein  = goal_protein
        current_user.goal_fat      = goal_fat
        current_user.goal_sugar    = goal_sugar
        db.session.commit()

        flash("Profile and coaching preferences updated.")
        return redirect(url_for("auth.profile"))

    pref = get_or_create_user_preferences(current_user.id)
    return render_template("profile.html", active_page="profile", profile=current_user, pref=pref)


@auth_bp.route("/forgot-password", methods=["GET"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    return render_template("forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET"])
def reset_password(token):
    # Deprecated in favor of Firebase Native Reset
    return redirect(url_for("auth.login"))
