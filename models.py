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
    weight_logs = db.relationship('WeightLog', backref='user', lazy=True, cascade="all, delete-orphan")
    food_favorites = db.relationship('FoodFavorite', backref='user', lazy=True, cascade="all, delete-orphan")
    saved_meals = db.relationship('SavedMeal', backref='user', lazy=True, cascade="all, delete-orphan")
    preferences = db.relationship('UserPreference', backref='user', uselist=False, lazy=True, cascade="all, delete-orphan")
    pending_drafts = db.relationship('PendingLogDraft', backref='user', lazy=True, cascade="all, delete-orphan")

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
    provenance = db.Column(db.String(50), nullable=True)  # "catalog", "custom", "ai_estimated", or None (legacy)

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

    sets_detail = db.relationship('WorkoutSet', backref='gym_log', lazy=True, cascade="all, delete-orphan", order_by="WorkoutSet.set_number")

    __table_args__ = (
        db.Index('idx_gym_log_user_date', 'user_id', 'date'),
    )


class WeightLog(db.Model):
    """Historical dated body-weight entries."""
    __tablename__ = "weight_logs"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.String(50), nullable=False, default=lambda: utc_iso(now_utc()))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'date', name='uq_weight_user_date'),
        db.Index('idx_weight_log_user_date', 'user_id', 'date'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date,
            "weight": self.weight,
            "notes": self.notes or "",
            "created_at": self.created_at,
        }


class FoodFavorite(db.Model):
    """User favorite foods for fast 1-click selection."""
    __tablename__ = "food_favorites"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    meal_category = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.String(50), nullable=False, default=lambda: utc_iso(now_utc()))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'meal_category', 'name', name='uq_fav_user_cat_name'),
        db.Index('idx_fav_user_cat', 'user_id', 'meal_category'),
    )


class SavedMeal(db.Model):
    """Saved reusable food combinations / meal templates."""
    __tablename__ = "saved_meals"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    meal_category = db.Column(db.String(50), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.String(50), nullable=False, default=lambda: utc_iso(now_utc()))

    items = db.relationship('SavedMealItem', backref='saved_meal', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "meal_category": self.meal_category,
            "notes": self.notes or "",
            "total_calories": round(sum(item.calories for item in self.items), 1),
            "total_protein": round(sum(item.protein for item in self.items), 1),
            "total_fat": round(sum(item.fat for item in self.items), 1),
            "total_sugar": round(sum(item.sugar for item in self.items), 1),
            "items": [item.to_dict() for item in self.items],
        }


class SavedMealItem(db.Model):
    """Individual food item within a saved meal template."""
    __tablename__ = "saved_meal_items"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    saved_meal_id = db.Column(db.Integer, db.ForeignKey('saved_meals.id', ondelete='CASCADE'), nullable=False)
    food = db.Column(db.String(100), nullable=False)
    qty = db.Column(db.Float, nullable=False, default=1.0)
    calories = db.Column(db.Float, nullable=False)
    protein = db.Column(db.Float, nullable=False, default=0.0)
    fat = db.Column(db.Float, nullable=False, default=0.0)
    sugar = db.Column(db.Float, nullable=False, default=0.0)

    def to_dict(self):
        return {
            "id": self.id,
            "food": self.food,
            "qty": self.qty,
            "calories": self.calories,
            "protein": self.protein,
            "fat": self.fat,
            "sugar": self.sugar,
        }


class WorkoutSet(db.Model):
    """Set-by-set strength workout records."""
    __tablename__ = "workout_sets"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    gym_log_id = db.Column(db.Integer, db.ForeignKey('gym_log.id', ondelete='CASCADE'), nullable=False)
    set_number = db.Column(db.Integer, nullable=False)
    reps = db.Column(db.Integer, nullable=False)
    weight = db.Column(db.Float, nullable=False, default=0.0)
    completed = db.Column(db.Boolean, nullable=False, default=True)
    rpe = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.String(50), nullable=False, default=lambda: utc_iso(now_utc()))

    __table_args__ = (
        db.Index('idx_workout_set_gym_log', 'gym_log_id', 'set_number'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "set_number": self.set_number,
            "reps": self.reps,
            "weight": self.weight,
            "completed": self.completed,
            "rpe": self.rpe,
        }


class UserPreference(db.Model):
    """User preferences, goals, and constraints for personalized coaching."""
    __tablename__ = "user_preferences"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)
    fitness_goal = db.Column(db.String(50), nullable=False, default='maintenance')
    diet_type = db.Column(db.String(50), nullable=False, default='standard')
    experience_level = db.Column(db.String(50), nullable=False, default='intermediate')
    equipment_access = db.Column(db.String(50), nullable=False, default='full_gym')
    target_sleep_hours = db.Column(db.Float, nullable=False, default=8.0)
    activity_level = db.Column(db.String(50), nullable=False, default='moderate')
    gender = db.Column(db.String(20), nullable=False, default='unspecified')
    injury_notes = db.Column(db.Text, nullable=True)
    custom_coaching_notes = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.String(50), nullable=False, default=lambda: utc_iso(now_utc()))

    def to_dict(self):
        return {
            "fitness_goal": self.fitness_goal,
            "diet_type": self.diet_type,
            "experience_level": self.experience_level,
            "equipment_access": self.equipment_access,
            "target_sleep_hours": self.target_sleep_hours,
            "activity_level": self.activity_level,
            "gender": self.gender,
            "injury_notes": self.injury_notes or "",
            "custom_coaching_notes": self.custom_coaching_notes or "",
        }


class RateLimitEvent(db.Model):
    """Tracks rate limiting events for multi-worker production deployments."""
    __tablename__ = "rate_limit_events"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    key = db.Column(db.String(150), nullable=False, index=True)
    timestamp = db.Column(db.Float, nullable=False, index=True)


class PendingLogDraft(db.Model):
    """Tracks active conversational logging drafts with explicit state machine and expiry."""
    __tablename__ = "pending_log_drafts"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    draft_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    log_type = db.Column(db.String(20), nullable=False)  # "food" or "workout"
    state = db.Column(db.String(30), nullable=False, default="collecting")  # "collecting", "awaiting_confirmation", "confirmed", "cancelled", "expired"
    draft_data = db.Column(db.Text, nullable=False)  # JSON string
    missing_fields = db.Column(db.Text, nullable=True)  # JSON string
    clarification_prompt = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.String(50), nullable=False, default=lambda: utc_iso(now_utc()))
    updated_at = db.Column(db.String(50), nullable=False, default=lambda: utc_iso(now_utc()))
    expires_at = db.Column(db.String(50), nullable=False, default=lambda: utc_iso(now_utc() + timedelta(minutes=30)))

    __table_args__ = (
        db.Index('idx_draft_user_state', 'user_id', 'state'),
    )

    def is_expired(self):
        try:
            exp = parse_utc_iso(self.expires_at)
            return now_utc() > exp
        except Exception:
            return False

    def touch(self):
        self.updated_at = utc_iso(now_utc())
        self.expires_at = utc_iso(now_utc() + timedelta(minutes=30))

    def get_data(self):
        import json as _json
        try:
            return _json.loads(self.draft_data) if self.draft_data else {}
        except Exception:
            return {}

    def set_data(self, data):
        import json as _json
        self.draft_data = _json.dumps(data)

    def to_dict(self):
        import json as _json
        try:
            parsed_data = _json.loads(self.draft_data) if self.draft_data else {}
        except Exception:
            parsed_data = {}
        try:
            missing = _json.loads(self.missing_fields) if self.missing_fields else []
        except Exception:
            missing = []
        return {
            "draft_id": self.draft_id,
            "log_type": self.log_type,
            "state": self.state,
            "data": parsed_data,
            "missing_fields": missing,
            "clarification_prompt": self.clarification_prompt,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
        }


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
    return db.session.get(User, user_id)


def get_user_by_email(email):
    return User.query.filter(User.email.ilike(email)).first()


def parse_admin_emails():
    raw = os.environ.get("ADMIN_EMAILS", "")
    return {email.strip().lower() for email in raw.split(",") if email.strip()}


def default_role_for_email(email):
    """Determine role for an email.
    
    Security note: Public registration must never automatically grant administrator privileges
    merely because the user is the first account in an empty database. Administrators must
    be explicitly designated via the ADMIN_EMAILS environment variable.
    """
    if email.lower() in parse_admin_emails():
        return "admin"
    return "user"


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


def get_or_create_user_preferences(user_id):
    """Retrieve user preference record, creating a default one if none exists."""
    pref = UserPreference.query.filter_by(user_id=user_id).first()
    if not pref:
        pref = UserPreference(
            user_id=user_id,
            fitness_goal="maintenance",
            diet_type="standard",
            experience_level="intermediate",
            equipment_access="full_gym",
            target_sleep_hours=8.0,
            activity_level="moderate",
            gender="unspecified",
        )
        db.session.add(pref)
        db.session.commit()
    return pref


def record_weight_log(user_id, date_str, weight_kg, notes=None):
    """Upsert a dated body-weight reading and sync the user's current profile weight."""
    entry = WeightLog.query.filter_by(user_id=user_id, date=date_str).first()
    if not entry:
        entry = WeightLog(user_id=user_id, date=date_str, weight=weight_kg, notes=notes)
        db.session.add(entry)
    else:
        entry.weight = weight_kg
        if notes is not None:
            entry.notes = notes

    # Sync latest weigh-in to User profile weight
    latest_entry = (
        WeightLog.query.filter_by(user_id=user_id)
        .order_by(WeightLog.date.desc())
        .first()
    )
    if not latest_entry or date_str >= latest_entry.date:
        user = db.session.get(User, user_id)
        if user:
            user.weight = weight_kg

    db.session.commit()
    return entry
