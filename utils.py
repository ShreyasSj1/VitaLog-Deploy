from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse, urljoin
from flask import request, has_request_context

def parse_optional_int(value):
    value = (value or "").strip()
    return int(value) if value else None

def parse_optional_float(value):
    value = (value or "").strip()
    return float(value) if value else None

def is_safe_redirect_target(target):
    if not target:
        return False
    host_url = urlparse(request.host_url)
    redirect_url = urlparse(urljoin(request.host_url, target))
    return redirect_url.scheme in ("http", "https") and host_url.netloc == redirect_url.netloc

def get_today():
    """Returns today's date, timezone-corrected using the client offset cookie if available."""
    try:
        if has_request_context():
            offset_minutes = request.cookies.get('timezone_offset')
            if offset_minutes:
                offset = int(offset_minutes)
                client_tz = timezone(-timedelta(minutes=offset))
                return datetime.now(client_tz).date()
    except Exception:
        pass
    return date.today()

def normalize_selected_date(raw_date):
    today = get_today()
    today_iso = today.isoformat()
    if not raw_date:
        return today_iso

    try:
        parsed = datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError:
        return today_iso

    return min(parsed, today).isoformat()

def get_week_dates(selected_date):
    d = datetime.strptime(selected_date, "%Y-%m-%d")
    # For the week swiper UI, we want the selected_date to be the last day in the swiper
    start = d - timedelta(days=6)
    return [(start + timedelta(days=i)).date().isoformat() for i in range(7)]
