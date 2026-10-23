import os
import json
import base64
from flask import Flask, redirect, url_for, session, request, Response, send_from_directory
from flask_login import LoginManager
import firebase_admin
from firebase_admin import credentials
from sqlalchemy.exc import SQLAlchemyError

from config import Config
from extensions import db
from models import get_user_by_id, seed_lookup_tables
from migrations import run_migrations
from csrf import generate_csrf_token, validate_csrf
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp

app = Flask(__name__)
app.config.from_object(Config)

from werkzeug.middleware.proxy_fix import ProxyFix

# Configure ProxyFix so request.remote_addr safely reflects the nearest trusted proxy hop (Render / Cloudflare)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.init_app(app)

@app.before_request
def check_csrf():
    validate_csrf()

@app.after_request
def apply_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Strict-Transport-Security (HSTS)
    if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https" or not app.debug:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://www.gstatic.com https://apis.google.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self' https://*.googleapis.com https://*.firebaseio.com https://identitytoolkit.googleapis.com; "
        "img-src 'self' data: https:; "
        "frame-ancestors 'self';"
    )
    response.headers["Content-Security-Policy"] = csp
    return response

@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(int(user_id))

@login_manager.unauthorized_handler
def unauthorized():
    session["next_url"] = request.url
    return redirect(url_for("auth.login"))

@app.context_processor
def inject_common_context():
    from utils import normalize_selected_date, get_week_dates
    selected_date = normalize_selected_date(request.args.get("date") or request.form.get("date"))
    week = get_week_dates(selected_date)
    return dict(
        csrf_token=generate_csrf_token(),
        firebase_api_key=app.config.get("FIREBASE_API_KEY", ""),
        firebase_auth_domain=app.config.get("FIREBASE_AUTH_DOMAIN", ""),
        firebase_project_id=app.config.get("FIREBASE_PROJECT_ID", ""),
        week=week,
    )


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

# ================= SEO / UTILITY ROUTES =================
@app.route("/robots.txt")
def robots_txt():
    host = request.host_url
    content = (
        "User-agent: *\n"
        "Allow: /login\n"
        "Allow: /register\n"
        "Allow: /forgot-password\n"
        "Disallow: /food\n"
        "Disallow: /sleep\n"
        "Disallow: /wellbeing\n"
        "Disallow: /gym\n"
        "Disallow: /report\n"
        "Disallow: /profile\n"
        "Disallow: /admin\n"
        "Disallow: /api\n"
        "Disallow: /logout\n"
        "\n"
        f"Sitemap: {host}sitemap.xml\n"
    )
    return Response(content, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    import datetime
    host = request.host_url.rstrip('/')
    today = datetime.date.today().isoformat()
    
    pages = [
        {"loc": f"{host}/login", "changefreq": "monthly", "priority": "0.8"},
        {"loc": f"{host}/register", "changefreq": "monthly", "priority": "0.8"},
        {"loc": f"{host}/forgot-password", "changefreq": "monthly", "priority": "0.5"},
    ]
    
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for page in pages:
        xml_content += '  <url>\n'
        xml_content += f'    <loc>{page["loc"]}</loc>\n'
        xml_content += f'    <lastmod>{today}</lastmod>\n'
        xml_content += f'    <changefreq>{page["changefreq"]}</changefreq>\n'
        xml_content += f'    <priority>{page["priority"]}</priority>\n'
        xml_content += '  </url>\n'
    xml_content += '</urlset>'
    
    return Response(xml_content, mimetype="application/xml")


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static", "icons"),
        "icon-192.png",
        mimetype="image/png"
    )


# ================= BLUEPRINTS =================
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)

with app.app_context():
    try:
        db.create_all()        # create any brand-new tables
        run_migrations()       # ALTER existing tables (add new columns safely)
        seed_lookup_tables()   # populate FoodItem / Exercise lookup tables
        app.config["BOOTSTRAP_STATUS"] = "ready"
    except SQLAlchemyError as e:
        app.config["BOOTSTRAP_STATUS"] = "failed"
        app.config["BOOTSTRAP_ERROR"] = str(e)
        print(f"[startup] Database bootstrap failed: {e}")
        # In production with an external database URL, raise to prevent silent corrupt deploys
        if not app.debug and os.environ.get("DATABASE_URL") and not os.environ.get("DATABASE_URL", "").startswith("sqlite:///:memory:"):
            raise

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    debug = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
