from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from firebase_admin import auth as firebase_auth

from extensions import db
from models import get_user_by_email, default_role_for_email, claim_legacy_rows, User
from utils import parse_optional_int, parse_optional_float

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/api/auth/firebase", methods=["POST"])
def auth_firebase():
    data = request.json
    id_token = data.get("idToken")
    name = data.get("name", "")
    
    if not id_token:
        return jsonify({"error": "No token provided"}), 400
        
    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        email = decoded_token.get('email', '').strip().lower()
    except Exception as e:
        print(f"Firebase token verification failed: {e}")
        return jsonify({"error": "Invalid token"}), 401

    if not email:
        return jsonify({"error": "Email is required"}), 400
        
    try:
        # Look up user or create them
        user = get_user_by_email(email)
        if not user:
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
            age = parse_optional_int(request.form.get("age"))
            height = parse_optional_float(request.form.get("height"))
            weight = parse_optional_float(request.form.get("weight"))
            goal_calories = parse_optional_float(request.form.get("goal_calories"))
            goal_protein  = parse_optional_float(request.form.get("goal_protein"))
            goal_fat      = parse_optional_float(request.form.get("goal_fat"))
            goal_sugar    = parse_optional_float(request.form.get("goal_sugar"))
        except ValueError:
            flash("Please enter valid numbers for all fields.")
            return redirect(url_for("auth.profile"))

        current_user.name          = name
        current_user.age           = age
        current_user.height        = height
        current_user.weight        = weight
        current_user.goal_calories = goal_calories
        current_user.goal_protein  = goal_protein
        current_user.goal_fat      = goal_fat
        current_user.goal_sugar    = goal_sugar
        db.session.commit()

        flash("Profile updated.")
        return redirect(url_for("auth.profile"))

    return render_template("profile.html", active_page="profile", profile=current_user)


@auth_bp.route("/forgot-password", methods=["GET"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    return render_template("forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET"])
def reset_password(token):
    # Deprecated in favor of Firebase Native Reset
    return redirect(url_for("auth.login"))
