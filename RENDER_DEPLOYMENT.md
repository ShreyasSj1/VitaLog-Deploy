# Render Deployment

This Flask app is ready to deploy on Render with PostgreSQL.

## Setup path

1. Push this repo to GitHub.
2. In Render, create a new `Postgres` database.
3. In Render, create a new `Web Service` from this repo.
4. Either let Render read `render.yaml`, or set the same values manually.
5. Set `DATABASE_URL` to the Render Postgres internal connection URL.
6. Deploy the web service.

## Service settings

- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app`
- Runtime: Python

## Required environment variables

- `DATABASE_URL` (Internal PostgreSQL connection string)
- `SECRET_KEY` (Strong random cryptographic key)
- `FLASK_DEBUG=false`
- `ADMIN_EMAILS` (Comma-separated list of initial administrator email addresses)
- `GROQ_API_KEY` (Required for the AI coaching chatbot)
- `FIREBASE_CREDENTIALS_BASE64` (Base64-encoded Firebase Service Account JSON, if using Firebase Auth)

## Administrator Bootstrap Procedure

For security, the application **never** automatically promotes the first registered user to administrator.
To establish an administrator account:

1. In Render Dashboard &rarr; **Environment Variables**, set `ADMIN_EMAILS` to your designated administrator email address:
   ```text
   ADMIN_EMAILS=admin@yourdomain.com
   ```
   (Multiple admins can be separated by commas, e.g. `admin1@example.com,admin2@example.com`).
2. Deploy the service with this variable set.
3. Register or sign in via that email. The user record is created with `role="admin"`, granting access to the `/admin/users` management panel.
4. Any user whose email is not in `ADMIN_EMAILS` is strictly granted `role="user"`.

## Health & Readiness Probes

- **Liveness:** `GET /health` (Returns 200 `{"ok": true, "status": "healthy"}`)
- **Readiness:** `GET /health/ready` (Verifies database connectivity and successful schema bootstrap; returns 503 if database is unreachable or migrations failed)

## Notes

- The app binds to `0.0.0.0` and uses `PORT`, as required by Render.
- On startup, the app automatically runs `db.create_all()`, versioned migrations via `run_migrations()` (using PostgreSQL advisory locks for multi-worker safety), and populates lookup tables.
- Do not use local SQLite in Render production because the web service filesystem is ephemeral.

## Optional migration

To move your current SQLite data into Postgres later:

```bash
export DATABASE_URL="your-render-postgres-url"
python3 scripts/migrate_sqlite_to_postgres.py
```
