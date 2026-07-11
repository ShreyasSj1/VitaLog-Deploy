import os
import json
import base64
from flask import Flask, redirect, url_for, session, request
from flask_login import LoginManager
import firebase_admin
from firebase_admin import credentials
from sqlalchemy.exc import SQLAlchemyError

from config import Config
from extensions import db
from models import get_user_by_id, seed_lookup_tables
from migrations import run_migrations
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(int(user_id))

@login_manager.unauthorized_handler
def unauthorized():
    session["next_url"] = request.url
    return redirect(url_for("auth.login"))

@app.context_processor
def inject_firebase_config():
    return dict(
        firebase_api_key=app.config.get("FIREBASE_API_KEY", ""),
        firebase_auth_domain=app.config.get("FIREBASE_AUTH_DOMAIN", ""),
        firebase_project_id=app.config.get("FIREBASE_PROJECT_ID", "")
    )

@app.context_processor
def inject_week_dates():
    from utils import normalize_selected_date, get_week_dates
    selected_date = normalize_selected_date(request.args.get("date") or request.form.get("date"))
    week = get_week_dates(selected_date)
    return dict(week=week)


# ================= FIREBASE ADMIN =================
firebase_credentials = os.environ.get("FIREBASE_CREDENTIALS_BASE64")
if firebase_credentials:
    cred_json = base64.b64decode(firebase_credentials).decode("utf-8")
    cred = credentials.Certificate(json.loads(cred_json))
    firebase_admin.initialize_app(cred)
elif os.path.exists("firebase-adminsdk.json"):
    cred = credentials.Certificate("firebase-adminsdk.json")
    firebase_admin.initialize_app(cred)
else:
    try:
        firebase_admin.initialize_app()
    except ValueError:
        pass

# ================= BLUEPRINTS =================
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)

with app.app_context():
    try:
        db.create_all()        # create any brand-new tables
        run_migrations()       # ALTER existing tables (add new columns safely)
        seed_lookup_tables()   # populate FoodItem / Exercise lookup tables
    except SQLAlchemyError as e:
        # Do not crash the web process at import time if DB is temporarily unreachable.
        # This keeps Render from restart-looping and makes debugging env/network issues easier.
        print(f"[startup] Database bootstrap skipped: {e}")

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    debug = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
