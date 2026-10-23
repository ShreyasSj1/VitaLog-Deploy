CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT,
    age INTEGER,
    height DOUBLE PRECISION,
    weight DOUBLE PRECISION,
    role TEXT NOT NULL DEFAULT 'user',
    is_active INTEGER NOT NULL DEFAULT 1,
    goal_calories DOUBLE PRECISION,
    goal_protein DOUBLE PRECISION,
    goal_fat DOUBLE PRECISION,
    goal_sugar DOUBLE PRECISION,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    conversation_id VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS food_log (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    date TEXT,
    meal TEXT,
    food TEXT,
    qty DOUBLE PRECISION,
    calories DOUBLE PRECISION,
    protein DOUBLE PRECISION,
    fat DOUBLE PRECISION,
    sugar DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS sleep_log (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    date TEXT,
    hours DOUBLE PRECISION,
    quality INTEGER,
    notes TEXT,
    UNIQUE(user_id, date)
);

CREATE TABLE IF NOT EXISTS wellbeing_log (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    date TEXT,
    activity TEXT,
    minutes INTEGER
);

CREATE TABLE IF NOT EXISTS gym_log (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    date TEXT,
    muscle TEXT,
    exercise TEXT,
    sets INTEGER,
    reps INTEGER,
    weight DOUBLE PRECISION,
    speed DOUBLE PRECISION,
    incline DOUBLE PRECISION,
    intensity TEXT,
    duration DOUBLE PRECISION,
    calories DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS weight_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date VARCHAR(20) NOT NULL,
    weight DOUBLE PRECISION NOT NULL,
    notes TEXT,
    created_at VARCHAR(50) NOT NULL,
    CONSTRAINT uq_weight_user_date UNIQUE (user_id, date)
);

CREATE TABLE IF NOT EXISTS food_favorites (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    meal_category VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    created_at VARCHAR(50) NOT NULL,
    CONSTRAINT uq_fav_user_cat_name UNIQUE (user_id, meal_category, name)
);

CREATE TABLE IF NOT EXISTS saved_meals (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    meal_category VARCHAR(50) NOT NULL,
    notes TEXT,
    created_at VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_meal_items (
    id BIGSERIAL PRIMARY KEY,
    saved_meal_id BIGINT NOT NULL REFERENCES saved_meals(id) ON DELETE CASCADE,
    food VARCHAR(100) NOT NULL,
    qty DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    calories DOUBLE PRECISION NOT NULL,
    protein DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    fat DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    sugar DOUBLE PRECISION NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS workout_sets (
    id BIGSERIAL PRIMARY KEY,
    gym_log_id BIGINT NOT NULL REFERENCES gym_log(id) ON DELETE CASCADE,
    set_number INTEGER NOT NULL,
    reps INTEGER NOT NULL,
    weight DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    completed BOOLEAN NOT NULL DEFAULT TRUE,
    rpe DOUBLE PRECISION,
    created_at VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS user_preferences (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    fitness_goal VARCHAR(50) NOT NULL DEFAULT 'maintenance',
    diet_type VARCHAR(50) NOT NULL DEFAULT 'standard',
    experience_level VARCHAR(50) NOT NULL DEFAULT 'intermediate',
    equipment_access VARCHAR(50) NOT NULL DEFAULT 'full_gym',
    target_sleep_hours DOUBLE PRECISION NOT NULL DEFAULT 8.0,
    activity_level VARCHAR(50) NOT NULL DEFAULT 'moderate',
    gender VARCHAR(20) NOT NULL DEFAULT 'unspecified',
    injury_notes TEXT,
    custom_coaching_notes TEXT,
    updated_at VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS food_items (
    id BIGSERIAL PRIMARY KEY,
    meal_category VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    calories DOUBLE PRECISION NOT NULL,
    protein DOUBLE PRECISION NOT NULL,
    fat DOUBLE PRECISION NOT NULL,
    sugar DOUBLE PRECISION NOT NULL,
    is_custom BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_food_item_category_name UNIQUE (meal_category, name)
);

CREATE TABLE IF NOT EXISTS exercises (
    id BIGSERIAL PRIMARY KEY,
    muscle_group VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL UNIQUE,
    is_cardio BOOLEAN NOT NULL DEFAULT FALSE,
    cardio_meta TEXT,
    is_custom BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    applied_at VARCHAR(50) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_food_log_user_date ON food_log(user_id, date);
CREATE INDEX IF NOT EXISTS idx_sleep_log_user_date ON sleep_log(user_id, date);
CREATE INDEX IF NOT EXISTS idx_wellbeing_log_user_date ON wellbeing_log(user_id, date);
CREATE INDEX IF NOT EXISTS idx_gym_log_user_date ON gym_log(user_id, date);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token ON password_reset_tokens(token);
CREATE INDEX IF NOT EXISTS idx_chat_user_created ON chat_messages(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_weight_log_user_date ON weight_logs (user_id, date);
CREATE INDEX IF NOT EXISTS idx_fav_user_cat ON food_favorites (user_id, meal_category);
CREATE INDEX IF NOT EXISTS idx_workout_set_gym_log ON workout_sets (gym_log_id, set_number);
