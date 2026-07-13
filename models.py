import os
import secrets
from datetime import datetime, timedelta, timezone
from werkzeug.security import check_password_hash, generate_password_hash
from flask_login import UserMixin
from extensions import db

def now_utc():
    return datetime.now(timezone.utc)

def utc_iso(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()

def parse_utc_iso(value):
    return datetime.fromisoformat(value)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(100))
    age = db.Column(db.Integer)
    height = db.Column(db.Float)
    weight = db.Column(db.Float)
    role = db.Column(db.String(20), nullable=False, default='user')
    is_active = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.String(50), nullable=False, default=lambda: utc_iso(now_utc()))

    # ── Per-user daily goals (fall back to app defaults when NULL) ─────────
    goal_calories = db.Column(db.Float)
    goal_protein  = db.Column(db.Float)
    goal_fat      = db.Column(db.Float)
    goal_sugar    = db.Column(db.Float)

    food_logs = db.relationship('FoodLog', backref='user', lazy=True, cascade="all, delete-orphan")
    sleep_logs = db.relationship('SleepLog', backref='user', lazy=True, cascade="all, delete-orphan")
    wellbeing_logs = db.relationship('WellbeingLog', backref='user', lazy=True, cascade="all, delete-orphan")
    gym_logs = db.relationship('GymLog', backref='user', lazy=True, cascade="all, delete-orphan")
    reset_tokens = db.relationship('PasswordResetToken', backref='user', lazy=True, cascade="all, delete-orphan")
    chat_messages = db.relationship('ChatMessage', backref='user', lazy=True, cascade="all, delete-orphan")

    @property
    def goals(self):
        """Return this user's daily goals, falling back to app-wide defaults."""
        from constants import GOALS as _DEFAULTS
        return {
            "calories": self.goal_calories if self.goal_calories is not None else _DEFAULTS["calories"],
            "protein":  self.goal_protein  if self.goal_protein  is not None else _DEFAULTS["protein"],
            "fat":      self.goal_fat      if self.goal_fat      is not None else _DEFAULTS["fat"],
            "sugar":    self.goal_sugar    if self.goal_sugar    is not None else _DEFAULTS["sugar"],
        }



class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.String(50), nullable=False)
    used_at = db.Column(db.String(50))
    created_at = db.Column(db.String(50), nullable=False, default=lambda: utc_iso(now_utc()))


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # "user" or "assistant"
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    conversation_id = db.Column(db.String(100), nullable=True)

    __table_args__ = (
        db.Index('idx_chat_user_created', 'user_id', 'created_at'),
    )


class FoodLog(db.Model):
    __tablename__ = "food_log"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'))
    date = db.Column(db.String(20))
    meal = db.Column(db.String(50))
    food = db.Column(db.String(100))
    qty = db.Column(db.Float)
    calories = db.Column(db.Float)
    protein = db.Column(db.Float)
    fat = db.Column(db.Float)
    sugar = db.Column(db.Float)

    __table_args__ = (
        db.Index('idx_food_log_user_date', 'user_id', 'date'),
    )


class SleepLog(db.Model):
    __tablename__ = "sleep_log"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'))
    date = db.Column(db.String(20))
    hours = db.Column(db.Float)
    quality = db.Column(db.Integer)
    notes = db.Column(db.Text)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'date', name='uq_sleep_user_date'),
        db.Index('idx_sleep_log_user_date', 'user_id', 'date'),
    )


class WellbeingLog(db.Model):
    __tablename__ = "wellbeing_log"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'))
    date = db.Column(db.String(20))
    activity = db.Column(db.String(100))
    minutes = db.Column(db.Integer)

    __table_args__ = (
        db.Index('idx_wellbeing_log_user_date', 'user_id', 'date'),
    )


class GymLog(db.Model):
    __tablename__ = "gym_log"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'))
    date = db.Column(db.String(20))
    muscle = db.Column(db.String(50))
    exercise = db.Column(db.String(100))
    sets = db.Column(db.Integer)
    reps = db.Column(db.Integer)
    weight = db.Column(db.Float)
    speed = db.Column(db.Float)
    incline = db.Column(db.Float)
    intensity = db.Column(db.String(50))
    duration = db.Column(db.Float)
    calories = db.Column(db.Float)

    __table_args__ = (
        db.Index('idx_gym_log_user_date', 'user_id', 'date'),
    )


# ──────────────────────────────────────────────
# LOOKUP TABLES  (populated by seed on startup)
# ──────────────────────────────────────────────

class FoodItem(db.Model):
    """Reference table for known foods with their nutritional data per serving."""
    __tablename__ = "food_items"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    meal_category = db.Column(db.String(50), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    calories = db.Column(db.Float, nullable=False)
    protein = db.Column(db.Float, nullable=False)
    fat = db.Column(db.Float, nullable=False)
    sugar = db.Column(db.Float, nullable=False)
    is_custom = db.Column(db.Boolean, nullable=False, default=False)

    __table_args__ = (
        db.UniqueConstraint('meal_category', 'name', name='uq_food_item_category_name'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "meal_category": self.meal_category,
            "name": self.name,
            "calories": self.calories,
            "protein": self.protein,
            "fat": self.fat,
            "sugar": self.sugar,
            "is_custom": self.is_custom,
        }


class Exercise(db.Model):
    """Reference table for known exercises with their muscle group and cardio flag."""
    __tablename__ = "exercises"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    muscle_group = db.Column(db.String(50), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    is_cardio = db.Column(db.Boolean, nullable=False, default=False)
    # Cardio-specific metadata (stored as JSON string for portability)
    cardio_meta = db.Column(db.Text)
    is_custom = db.Column(db.Boolean, nullable=False, default=False)

    def to_dict(self):
        return {
            "id": self.id,
            "muscle_group": self.muscle_group,
            "name": self.name,
            "is_cardio": self.is_cardio,
            "is_custom": self.is_custom,
        }


def seed_lookup_tables():
    """Populate FoodItem and Exercise tables from constants.py.

    Idempotent — uses INSERT OR IGNORE semantics so it's safe to run on every
    startup without creating duplicates.
    """
    import json as _json
    from constants import FOOD_DATA, EXERCISE_CATALOG, CARDIO_EXERCISES, CARDIO_META

    # ── Food items ────────────────────────────────────────────────────────
    existing_food_keys = {
        (fi.meal_category, fi.name)
        for fi in FoodItem.query.with_entities(FoodItem.meal_category, FoodItem.name).all()
    }
    new_foods = []
    for category, items in FOOD_DATA.items():
        for name, (cal, pro, fat, sug) in items.items():
            if (category, name) not in existing_food_keys:
                new_foods.append(FoodItem(
                    meal_category=category,
                    name=name,
                    calories=cal,
                    protein=pro,
                    fat=fat,
                    sugar=sug,
                    is_custom=False,
                ))
    if new_foods:
        db.session.bulk_save_objects(new_foods)

    # ── Exercises ─────────────────────────────────────────────────────────
    existing_exercise_names = {
        e.name for e in Exercise.query.with_entities(Exercise.name).all()
    }
    new_exercises = []
    for muscle_group, exercise_names in EXERCISE_CATALOG.items():
        for ex_name in exercise_names:
            if ex_name not in existing_exercise_names:
                is_cardio = ex_name in CARDIO_EXERCISES
                meta_json = _json.dumps(CARDIO_META[ex_name]) if is_cardio and ex_name in CARDIO_META else None
                new_exercises.append(Exercise(
                    muscle_group=muscle_group,
                    name=ex_name,
                    is_cardio=is_cardio,
                    cardio_meta=meta_json,
                    is_custom=False,
                ))
    if new_exercises:
        db.session.bulk_save_objects(new_exercises)

    db.session.commit()


def get_user_by_id(user_id):
    return User.query.get(user_id)


def get_user_by_email(email):
    return User.query.filter(User.email.ilike(email)).first()


def parse_admin_emails():
    raw = os.environ.get("ADMIN_EMAILS", "")
    return {email.strip().lower() for email in raw.split(",") if email.strip()}


def default_role_for_email(email):
    if email.lower() in parse_admin_emails():
        return "admin"
    user_count = User.query.count()
    return "admin" if user_count == 0 else "user"


def claim_legacy_rows(user_id):
    user_count = User.query.count()
    if user_count != 1:
        return

    FoodLog.query.filter(FoodLog.user_id.is_(None)).update({"user_id": user_id})
    SleepLog.query.filter(SleepLog.user_id.is_(None)).update({"user_id": user_id})
    WellbeingLog.query.filter(WellbeingLog.user_id.is_(None)).update({"user_id": user_id})
    GymLog.query.filter(GymLog.user_id.is_(None)).update({"user_id": user_id})
    db.session.commit()


def create_user(name, email, password):
    normalized_email = email.strip().lower()
    existing = get_user_by_email(normalized_email)
    if existing:
        return None, "An account with that email already exists."

    role = default_role_for_email(normalized_email)
    user = User(
        email=normalized_email,
        password_hash=generate_password_hash(password),
        name=name.strip() or normalized_email,
        role=role,
        is_active=1
    )
    db.session.add(user)
    db.session.commit()
    claim_legacy_rows(user.id)
    return user, None


def issue_password_reset_token(email):
    normalized_email = email.strip().lower()
    user = get_user_by_email(normalized_email)
    if not user:
        return None

    PasswordResetToken.query.filter_by(user_id=user.id, used_at=None).update({"used_at": utc_iso(now_utc())})

    token = secrets.token_urlsafe(32)
    expires_at = now_utc() + timedelta(minutes=30)
    reset_token = PasswordResetToken(
        user_id=user.id,
        token=token,
        expires_at=utc_iso(expires_at)
    )
    db.session.add(reset_token)
    db.session.commit()
    return token


def get_valid_password_reset_token(token):
    token_row = PasswordResetToken.query.filter_by(token=token).first()
    if not token_row or token_row.used_at:
        return None
    if parse_utc_iso(token_row.expires_at) < now_utc():
        return None
    return token_row


def consume_password_reset_token(token, new_password):
    token_row = get_valid_password_reset_token(token)
    if not token_row:
        return False

    used_at = utc_iso(now_utc())
    user = User.query.get(token_row.user_id)
    user.password_hash = generate_password_hash(new_password)
    
    token_row.used_at = used_at
    PasswordResetToken.query.filter(
        PasswordResetToken.user_id == token_row.user_id,
        PasswordResetToken.token != token,
        PasswordResetToken.used_at.is_(None)
    ).update({"used_at": used_at})
    
    db.session.commit()
    return True
