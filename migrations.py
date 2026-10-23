"""
migrations.py — Controlled, versioned schema migration system for VitalLog.

Maintains a `schema_migrations` tracking table so every migration runs exactly once
in a deterministic, version-controlled sequence.

Guarantees:
- Fully idempotent: can run safely on fresh databases, local SQLite, or production PostgreSQL.
- Preserves all historical data without dropping or resetting tables.
- Supports both SQLite (PRAGMA inspection) and PostgreSQL (IF NOT EXISTS DDL).
"""
import datetime
from extensions import db


def _get_applied_versions(conn) -> set:
    """Return the set of already applied migration versions."""
    # Ensure tracking table exists
    conn.execute(db.text("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            applied_at VARCHAR(50) NOT NULL
        )
    """))
    conn.commit()

    rows = conn.execute(db.text("SELECT version FROM schema_migrations")).fetchall()
    return {row[0] for row in rows}


def _record_migration(conn, version: int, name: str, dialect: str = "sqlite"):
    """Record that a migration version has succeeded."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if dialect == "postgresql":
        conn.execute(
            db.text("INSERT INTO schema_migrations (version, name, applied_at) VALUES (:v, :n, :t) ON CONFLICT (version) DO NOTHING"),
            {"v": version, "n": name, "t": now_iso}
        )
    else:
        conn.execute(
            db.text("INSERT OR IGNORE INTO schema_migrations (version, name, applied_at) VALUES (:v, :n, :t)"),
            {"v": version, "n": name, "t": now_iso}
        )
    conn.commit()


# ===========================================================================
# Migration Definitions
# ===========================================================================

def migration_001_phase5_user_goals(conn, dialect: str):
    """Add goal columns to users table."""
    if dialect == "postgresql":
        conn.execute(db.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS goal_calories FLOAT"))
        conn.execute(db.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS goal_protein FLOAT"))
        conn.execute(db.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS goal_fat FLOAT"))
        conn.execute(db.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS goal_sugar FLOAT"))
    else:
        existing = {row[1] for row in conn.execute(db.text("PRAGMA table_info(users)"))}
        for col in ("goal_calories", "goal_protein", "goal_fat", "goal_sugar"):
            if col not in existing:
                conn.execute(db.text(f"ALTER TABLE users ADD COLUMN {col} FLOAT"))
    conn.commit()


def migration_002_dated_weight_logs(conn, dialect: str):
    """Create weight_logs table for historical body weight tracking."""
    if dialect == "postgresql":
        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS weight_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                date VARCHAR(20) NOT NULL,
                weight FLOAT NOT NULL,
                notes TEXT,
                created_at VARCHAR(50) NOT NULL,
                CONSTRAINT uq_weight_user_date UNIQUE (user_id, date)
            )
        """))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_weight_log_user_date ON weight_logs (user_id, date)"))
    else:
        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS weight_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                date VARCHAR(20) NOT NULL,
                weight FLOAT NOT NULL,
                notes TEXT,
                created_at VARCHAR(50) NOT NULL,
                CONSTRAINT uq_weight_user_date UNIQUE (user_id, date)
            )
        """))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_weight_log_user_date ON weight_logs (user_id, date)"))
    conn.commit()


def migration_003_nutrition_favorites_and_saved_meals(conn, dialect: str):
    """Create food_favorites, saved_meals, and saved_meal_items tables."""
    if dialect == "postgresql":
        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS food_favorites (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                meal_category VARCHAR(50) NOT NULL,
                name VARCHAR(100) NOT NULL,
                created_at VARCHAR(50) NOT NULL,
                CONSTRAINT uq_fav_user_cat_name UNIQUE (user_id, meal_category, name)
            )
        """))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_fav_user_cat ON food_favorites (user_id, meal_category)"))

        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS saved_meals (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name VARCHAR(100) NOT NULL,
                meal_category VARCHAR(50) NOT NULL,
                notes TEXT,
                created_at VARCHAR(50) NOT NULL
            )
        """))

        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS saved_meal_items (
                id SERIAL PRIMARY KEY,
                saved_meal_id INTEGER NOT NULL REFERENCES saved_meals(id) ON DELETE CASCADE,
                food VARCHAR(100) NOT NULL,
                qty FLOAT NOT NULL DEFAULT 1.0,
                calories FLOAT NOT NULL,
                protein FLOAT NOT NULL DEFAULT 0.0,
                fat FLOAT NOT NULL DEFAULT 0.0,
                sugar FLOAT NOT NULL DEFAULT 0.0
            )
        """))
    else:
        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS food_favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                meal_category VARCHAR(50) NOT NULL,
                name VARCHAR(100) NOT NULL,
                created_at VARCHAR(50) NOT NULL,
                CONSTRAINT uq_fav_user_cat_name UNIQUE (user_id, meal_category, name)
            )
        """))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_fav_user_cat ON food_favorites (user_id, meal_category)"))

        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS saved_meals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name VARCHAR(100) NOT NULL,
                meal_category VARCHAR(50) NOT NULL,
                notes TEXT,
                created_at VARCHAR(50) NOT NULL
            )
        """))

        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS saved_meal_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                saved_meal_id INTEGER NOT NULL REFERENCES saved_meals(id) ON DELETE CASCADE,
                food VARCHAR(100) NOT NULL,
                qty FLOAT NOT NULL DEFAULT 1.0,
                calories FLOAT NOT NULL,
                protein FLOAT NOT NULL DEFAULT 0.0,
                fat FLOAT NOT NULL DEFAULT 0.0,
                sugar FLOAT NOT NULL DEFAULT 0.0
            )
        """))
    conn.commit()


def migration_004_workout_sets(conn, dialect: str):
    """Create workout_sets table for set-by-set exercise tracking."""
    if dialect == "postgresql":
        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS workout_sets (
                id SERIAL PRIMARY KEY,
                gym_log_id INTEGER NOT NULL REFERENCES gym_log(id) ON DELETE CASCADE,
                set_number INTEGER NOT NULL,
                reps INTEGER NOT NULL,
                weight FLOAT NOT NULL DEFAULT 0.0,
                completed BOOLEAN NOT NULL DEFAULT TRUE,
                rpe FLOAT,
                created_at VARCHAR(50) NOT NULL
            )
        """))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_workout_set_gym_log ON workout_sets (gym_log_id, set_number)"))
    else:
        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS workout_sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gym_log_id INTEGER NOT NULL REFERENCES gym_log(id) ON DELETE CASCADE,
                set_number INTEGER NOT NULL,
                reps INTEGER NOT NULL,
                weight FLOAT NOT NULL DEFAULT 0.0,
                completed BOOLEAN NOT NULL DEFAULT 1,
                rpe FLOAT,
                created_at VARCHAR(50) NOT NULL
            )
        """))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_workout_set_gym_log ON workout_sets (gym_log_id, set_number)"))
    conn.commit()


def migration_005_user_preferences(conn, dialect: str):
    """Create user_preferences table for coaching and personalized target setting."""
    if dialect == "postgresql":
        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                fitness_goal VARCHAR(50) NOT NULL DEFAULT 'maintenance',
                diet_type VARCHAR(50) NOT NULL DEFAULT 'standard',
                experience_level VARCHAR(50) NOT NULL DEFAULT 'intermediate',
                equipment_access VARCHAR(50) NOT NULL DEFAULT 'full_gym',
                target_sleep_hours FLOAT NOT NULL DEFAULT 8.0,
                activity_level VARCHAR(50) NOT NULL DEFAULT 'moderate',
                gender VARCHAR(20) NOT NULL DEFAULT 'unspecified',
                injury_notes TEXT,
                custom_coaching_notes TEXT,
                updated_at VARCHAR(50) NOT NULL
            )
        """))
    else:
        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                fitness_goal VARCHAR(50) NOT NULL DEFAULT 'maintenance',
                diet_type VARCHAR(50) NOT NULL DEFAULT 'standard',
                experience_level VARCHAR(50) NOT NULL DEFAULT 'intermediate',
                equipment_access VARCHAR(50) NOT NULL DEFAULT 'full_gym',
                target_sleep_hours FLOAT NOT NULL DEFAULT 8.0,
                activity_level VARCHAR(50) NOT NULL DEFAULT 'moderate',
                gender VARCHAR(20) NOT NULL DEFAULT 'unspecified',
                injury_notes TEXT,
                custom_coaching_notes TEXT,
                updated_at VARCHAR(50) NOT NULL
            )
        """))
    conn.commit()


def migration_006_rate_limit_events(conn, dialect: str):
    """Create rate_limit_events table for multi-worker rate limiting."""
    if dialect == "postgresql":
        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS rate_limit_events (
                id SERIAL PRIMARY KEY,
                key VARCHAR(150) NOT NULL,
                timestamp DOUBLE PRECISION NOT NULL
            )
        """))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_rate_limit_key_ts ON rate_limit_events (key, timestamp)"))
    else:
        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS rate_limit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key VARCHAR(150) NOT NULL,
                timestamp REAL NOT NULL
            )
        """))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_rate_limit_key_ts ON rate_limit_events (key, timestamp)"))
    conn.commit()


def migration_007_food_log_provenance(conn, dialect: str):
    """Add provenance tracking column to food_log table."""
    if dialect == "postgresql":
        conn.execute(db.text("ALTER TABLE food_log ADD COLUMN IF NOT EXISTS provenance VARCHAR(50)"))
    else:
        existing = {row[1] for row in conn.execute(db.text("PRAGMA table_info(food_log)"))}
        if "provenance" not in existing:
            conn.execute(db.text("ALTER TABLE food_log ADD COLUMN provenance VARCHAR(50)"))
    conn.commit()


def migration_008_pending_log_drafts(conn, dialect: str):
    """Create pending_log_drafts table for conversational multi-turn draft state."""
    if dialect == "postgresql":
        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS pending_log_drafts (
                id SERIAL PRIMARY KEY,
                draft_id VARCHAR(64) NOT NULL UNIQUE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                log_type VARCHAR(20) NOT NULL,
                state VARCHAR(30) NOT NULL DEFAULT 'collecting',
                draft_data TEXT NOT NULL,
                missing_fields TEXT,
                clarification_prompt TEXT,
                created_at VARCHAR(50) NOT NULL,
                updated_at VARCHAR(50) NOT NULL,
                expires_at VARCHAR(50) NOT NULL
            )
        """))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_draft_user_state ON pending_log_drafts (user_id, state)"))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_draft_id ON pending_log_drafts (draft_id)"))
    else:
        conn.execute(db.text("""
            CREATE TABLE IF NOT EXISTS pending_log_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                draft_id VARCHAR(64) NOT NULL UNIQUE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                log_type VARCHAR(20) NOT NULL,
                state VARCHAR(30) NOT NULL DEFAULT 'collecting',
                draft_data TEXT NOT NULL,
                missing_fields TEXT,
                clarification_prompt TEXT,
                created_at VARCHAR(50) NOT NULL,
                updated_at VARCHAR(50) NOT NULL,
                expires_at VARCHAR(50) NOT NULL
            )
        """))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_draft_user_state ON pending_log_drafts (user_id, state)"))
        conn.execute(db.text("CREATE INDEX IF NOT EXISTS idx_draft_id ON pending_log_drafts (draft_id)"))
    conn.commit()


# Ordered list of all migrations
MIGRATIONS = [
    (1, "phase5_user_goals", migration_001_phase5_user_goals),
    (2, "dated_weight_logs", migration_002_dated_weight_logs),
    (3, "nutrition_favorites_and_saved_meals", migration_003_nutrition_favorites_and_saved_meals),
    (4, "workout_sets", migration_004_workout_sets),
    (5, "user_preferences", migration_005_user_preferences),
    (6, "rate_limit_events", migration_006_rate_limit_events),
    (7, "food_log_provenance", migration_007_food_log_provenance),
    (8, "pending_log_drafts", migration_008_pending_log_drafts),
]


def run_migrations():
    """Apply all pending schema changes in ordered version sequence."""
    engine = db.engine
    dialect = engine.dialect.name  # 'sqlite' or 'postgresql'

    with engine.connect() as conn:
        # If running on PostgreSQL with multiple Gunicorn workers, use an advisory lock
        # to guarantee migrations serialize safely across workers without DDL collisions.
        if dialect == "postgresql":
            conn.execute(db.text("SELECT pg_advisory_lock(74218942)"))
            conn.commit()

        try:
            applied = _get_applied_versions(conn)
            for version, name, func in MIGRATIONS:
                if version not in applied:
                    print(f"[migration] Applying migration {version:03d}_{name} on {dialect}...")
                    func(conn, dialect)
                    _record_migration(conn, version, name, dialect)
                    print(f"[migration] Successfully applied {version:03d}_{name}.")
        finally:
            if dialect == "postgresql":
                conn.execute(db.text("SELECT pg_advisory_unlock(74218942)"))
                conn.commit()
