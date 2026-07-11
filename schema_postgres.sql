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

CREATE INDEX IF NOT EXISTS idx_food_log_user_date ON food_log(user_id, date);
CREATE INDEX IF NOT EXISTS idx_sleep_log_user_date ON sleep_log(user_id, date);
CREATE INDEX IF NOT EXISTS idx_wellbeing_log_user_date ON wellbeing_log(user_id, date);
CREATE INDEX IF NOT EXISTS idx_gym_log_user_date ON gym_log(user_id, date);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token ON password_reset_tokens(token);
