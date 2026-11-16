# VitalLog

A health, nutrition, and fitness tracking web application built with Flask, SQLAlchemy, vanilla JavaScript, and Groq LLM integration. Features conversational natural-language logging, daily workout challenges, personal record tracking, and full Progressive Web App (PWA) support.

---

## Core Capabilities

- **Nutrition & Macro Tracking**: Log meals with automatic calorie, protein, fat, and sugar calculations. Includes favorite items, recent food suggestions, and custom saved meals.
- **Workout & Gym Logging**: Track strength sets, reps, weight, and cardio workouts with MET, speed, and incline calorie formulas. Tracks exercise history and personal records (PRs).
- **Conversational AI Assistant**: Log meals and workouts naturally through chat powered by Groq API (`llama-3.1-8b-instant`). Includes multi-turn memory, portion estimation, and interactive confirmation drafts.
- **Daily Workout Challenges (WOD)**: Curated daily fitness challenges with interactive countdown timers, form guides, and completion status.
- **Recovery & Wellness**: Daily sleep logs (hours and quality rating), wellbeing session tracking, and body weight logs with rolling trend calculations.
- **PWA Ready**: Offline support with service worker caching, install prompts for mobile and desktop, and app manifest.
- **Security & Data Integrity**: CSRF token validation on all state-modifying requests, multi-worker sliding window rate limiting, Content Security Policy (CSP), HSTS headers, and isolated multi-tenant data scoping.

---

## Prerequisites

- Python 3.11 or Python 3.12
- Git

---

## Local Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/vansh917917/VitaLog-Deploy.git
   cd VitaLog-Deploy
   ```

2. **Create and activate a virtual environment**:
   Using standard Python:
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS / Linux
   source .venv/bin/activate
   ```
   Or using `uv`:
   ```bash
   uv venv
   uv pip install -r requirements.txt --python .venv\Scripts\python.exe
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables (optional for local dev)**:
   Create a `.env` file in the root directory:
   ```env
   SECRET_KEY=your-local-dev-secret-key
   FLASK_DEBUG=true
   PORT=5002
   # Optional: add your Groq API key to test the conversational logger
   GROQ_API_KEY=your_groq_api_key_here
   ```
   If `DATABASE_URL` is omitted, the application automatically initializes a local SQLite database (`fitness.db`).

5. **Start the local server**:
   ```bash
   python app.py
   ```
   The application will run at `http://localhost:5002`.

---

## Configuration Reference

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `SECRET_KEY` | Yes (Production) | Dev fallback | Cryptographic key for session signing and CSRF validation |
| `DATABASE_URL` | No | `sqlite:///fitness.db` | PostgreSQL connection string or SQLite URI |
| `FLASK_DEBUG` | No | `true` | Enables Flask debug mode and reloaders |
| `PORT` | No | `5002` | Port on which the application listens |
| `GROQ_API_KEY` | No | `None` | API key for LLM-powered conversational food/gym logging |
| `ADMIN_EMAILS` | No | `None` | Comma-separated list of admin email addresses |
| `FIREBASE_API_KEY` | No | `""` | Firebase Web Client API key for client-side auth |
| `FIREBASE_AUTH_DOMAIN` | No | `""` | Firebase auth domain |
| `FIREBASE_PROJECT_ID` | No | `""` | Firebase project identifier |
| `FIREBASE_CREDENTIALS_BASE64` | No | `None` | Base64-encoded Firebase Admin service account JSON |

---

## Running the Test Suite

The project includes unit and integration tests across all models, authentication flows, chat memory, security gates, and endpoints:

```bash
pytest
```

Run tests with verbose output:
```bash
pytest -v
```

---

## Deployment

- **Render**: Configured with `render.yaml`. See [RENDER_DEPLOYMENT.md](file:///c:/Users/Vansh%20Gupta/Desktop/Programming/open%20source/VitaLog-Deploy/RENDER_DEPLOYMENT.md) for database provisioning, environment variables, and keep-alive configuration.
- **Railway**: Configured with `railway.json` using the Railpack builder. See [RAILWAY_DEPLOYMENT.md](file:///c:/Users/Vansh%20Gupta/Desktop/Programming/open%20source/VitaLog-Deploy/RAILWAY_DEPLOYMENT.md) for setup details.
