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

## Keep-alive on Render free tier

Render spins down free web services after 15 minutes of inactivity, causing cold starts on subsequent requests. VitalLog includes a multi-layer keep-alive strategy so the service remains responsive:

### 1. Internal Background Heartbeat (keep_alive.py & gunicorn.conf.py)
- **Zero configuration on Render**: Automatically resolves RENDER_EXTERNAL_URL, RENDER_EXTERNAL_HOSTNAME, or RENDER_SERVICE_NAME.
- **Immediate startup ping**: Pings 15 seconds after booting, then continues on a 7-minute recurring interval with 30-second transient retry.
- **Worker-safe**: Initialized in gunicorn.conf.py (post_worker_init) after worker processes fork, eliminating pre-fork thread drops.
- **Lightweight**: Hits the in-memory GET /health probe without touching the database.
- **Inert locally**: Does not spawn threads or pings when running without Render environment variables.

### 2. External GitHub Actions Heartbeat (.github/workflows/keep-alive.yml)
- Runs every 12 minutes on GitHub's cloud.
- Sends an external HTTP ping from outside Render's infrastructure, guaranteeing that even if Render restarts or suspends the container, the service is immediately woken up.
- By default targets https://vitallog-deploy.onrender.com/health. If your Render URL is different, set a repository secret or variable named RENDER_APP_URL.

### Environment variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| KEEP_ALIVE_ENABLED | true | Set to false to disable the internal heartbeat. |
| KEEP_ALIVE_INTERVAL_MINUTES | 7 | Ping interval in minutes (must be > 0 and < 14). |
| KEEP_ALIVE_URL | None | Optional manual URL override (e.g. custom domain). |

> [!NOTE]
> Combining the internal 7-minute heartbeat with the 12-minute external GitHub Actions ping ensures the service stays awake 24/7. A single free service uses approximately 720 to 744 hours per month, remaining within Render's 750 free instance hours allowance.

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
