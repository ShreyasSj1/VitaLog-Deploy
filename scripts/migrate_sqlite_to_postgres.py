import os
import sqlite3
from pathlib import Path

try:
    import psycopg
    from psycopg import sql
except ImportError as exc:
    raise SystemExit("psycopg is required. Install dependencies from requirements.txt first.") from exc


ROOT = Path(__file__).resolve().parents[1]
SQLITE_PATH = Path(os.environ.get("SQLITE_PATH", ROOT / "fitness.db"))
DATABASE_URL = os.environ.get("DATABASE_URL", "")

TABLES = [
    "users",
    "password_reset_tokens",
    "chat_messages",
    "food_log",
    "sleep_log",
    "wellbeing_log",
    "gym_log",
    "weight_logs",
    "food_favorites",
    "saved_meals",
    "saved_meal_items",
    "workout_sets",
    "user_preferences",
    "food_items",
    "exercises",
]


def load_schema():
    return (ROOT / "schema_postgres.sql").read_text(encoding="utf-8")


def sqlite_connection():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def postgres_connection():
    if not DATABASE_URL:
        raise SystemExit("Set DATABASE_URL to your PostgreSQL connection string before running this script.")
    return psycopg.connect(DATABASE_URL)


def copy_table(sqlite_conn, pg_conn, table_name):
    rows = sqlite_conn.execute(f"SELECT * FROM {table_name} ORDER BY id").fetchall()
    if not rows:
        return

    columns = list(rows[0].keys())
    quoted_columns = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    insert_sql = (
        f"INSERT INTO {table_name} ({quoted_columns}) VALUES ({placeholders}) "
        f"ON CONFLICT (id) DO NOTHING"
    )

    with pg_conn.cursor() as cur:
        for row in rows:
            cur.execute(insert_sql, tuple(row[column] for column in columns))


def reset_sequence(pg_conn, table_name):
    with pg_conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                """
                SELECT setval(
                    pg_get_serial_sequence(%s, 'id'),
                    COALESCE((SELECT MAX(id) FROM {table}), 1),
                    true
                )
                """
            ).format(table=sql.Identifier(table_name)),
            (table_name,),
        )


def main():
    if not SQLITE_PATH.exists():
        raise SystemExit(f"SQLite database not found at {SQLITE_PATH}")

    sqlite_conn = sqlite_connection()
    pg_conn = postgres_connection()

    try:
        with pg_conn.cursor() as cur:
            for statement in [stmt.strip() for stmt in load_schema().split(";") if stmt.strip()]:
                cur.execute(statement)

        for table_name in TABLES:
            copy_table(sqlite_conn, pg_conn, table_name)

        for table_name in TABLES:
            reset_sequence(pg_conn, table_name)

        pg_conn.commit()
        print("SQLite data migrated to PostgreSQL successfully.")
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
