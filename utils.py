import math
import time
import threading
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse, urljoin
from flask import request, has_request_context


# ===========================================================================
# Rate Limiting
# ===========================================================================

class InMemoryRateLimiter:
    """Thread-safe sliding-window in-memory rate limiter."""
    def __init__(self, requests_per_window: int = 30, window_seconds: int = 60):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self._history = defaultdict(deque)
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        if not key:
            return True
        now = time.time()
        cutoff = now - self.window_seconds
        with self._lock:
            queue = self._history[key]
            while queue and queue[0] < cutoff:
                queue.popleft()
            if len(queue) >= self.requests_per_window:
                return False
            queue.append(now)
            return True

    def reset(self):
        with self._lock:
            self._history.clear()


# Default rate limiter instances for sensitive endpoints
auth_rate_limiter = InMemoryRateLimiter(requests_per_window=15, window_seconds=60)
chat_rate_limiter = InMemoryRateLimiter(requests_per_window=20, window_seconds=60)


# ===========================================================================
# Parsing & Validation Helpers
# ===========================================================================

def parse_optional_int(value):
    value = (value or "").strip()
    return int(value) if value else None


def parse_optional_float(value):
    value = (value or "").strip()
    return float(value) if value else None


def validate_positive_float(value, field_name: str, min_val: float = 0.01, max_val: float = 10000.0) -> float:
    """Validate that value is a finite number > 0 within bounds."""
    try:
        val = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a valid number.")
    if math.isnan(val) or math.isinf(val):
        raise ValueError(f"{field_name} must be a finite number.")
    if val < min_val:
        raise ValueError(f"{field_name} must be greater than zero (minimum {min_val}).")
    if val > max_val:
        raise ValueError(f"{field_name} cannot exceed {max_val}.")
    return val


def validate_non_negative_float(value, field_name: str, max_val: float = 10000.0, allow_none: bool = False):
    """Validate that value is >= 0 and finite."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if allow_none:
            return None
        raise ValueError(f"{field_name} is required.")
    try:
        val = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a valid number.")
    if math.isnan(val) or math.isinf(val):
        raise ValueError(f"{field_name} must be a finite number.")
    if val < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    if val > max_val:
        raise ValueError(f"{field_name} cannot exceed {max_val}.")
    return val


def validate_int_range(value, field_name: str, min_val: int, max_val: int, allow_none: bool = False):
    """Validate that integer is within inclusive bounds [min_val, max_val]."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if allow_none:
            return None
        raise ValueError(f"{field_name} is required.")
    try:
        val = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a whole number.")
    if val < min_val or val > max_val:
        raise ValueError(f"{field_name} must be between {min_val} and {max_val}.")
    return val


def validate_text(value, field_name: str, min_len: int = 1, max_len: int = 100, allow_none: bool = False):
    """Validate trimmed text length."""
    val = (value or "").strip()
    if not val:
        if allow_none:
            return None
        raise ValueError(f"{field_name} cannot be empty.")
    if len(val) < min_len:
        raise ValueError(f"{field_name} must be at least {min_len} character(s).")
    if len(val) > max_len:
        raise ValueError(f"{field_name} cannot exceed {max_len} characters.")
    return val


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
    start = d - timedelta(days=6)
    return [(start + timedelta(days=i)).date().isoformat() for i in range(7)]


# ===========================================================================
# Energy Balance & TDEE Calculations
# ===========================================================================

def calculate_bmr_mifflin_st_jeor(weight_kg: float, height_cm: float, age: int, gender: str = "male") -> float:
    """Calculate Basal Metabolic Rate using the Mifflin-St Jeor formula.
    Returns 0.0 if any parameter is missing, non-positive, or non-finite.
    """
    if not weight_kg or not height_cm or not age:
        return 0.0
    try:
        w = float(weight_kg)
        h = float(height_cm)
        a = int(age)
    except (TypeError, ValueError):
        return 0.0
    if w <= 0 or h <= 0 or a <= 0 or math.isnan(w) or math.isinf(w) or math.isnan(h) or math.isinf(h):
        return 0.0

    # BMR = 10*weight + 6.25*height - 5*age (+5 for male, -161 for female)
    base = (10.0 * w) + (6.25 * h) - (5.0 * a)
    if (gender or "").lower() in ("female", "f"):
        return round(base - 161.0, 1)
    # Default to male / neutral formula (+5)
    return round(base + 5.0, 1)


def calculate_tdee(weight_kg: float, height_cm: float, age: int, gender: str = "male", activity_factor: float = 1.375) -> float:
    """Calculate Total Daily Energy Expenditure (BMR * Activity Multiplier).
    Activity levels:
    - 1.2: Sedentary (desk job, little exercise)
    - 1.375: Lightly active (light exercise 1-3 days/week)
    - 1.55: Moderately active (moderate exercise 3-5 days/week)
    - 1.725: Very active (hard exercise 6-7 days/week)
    Returns 0.0 if underlying BMR cannot be computed.
    """
    bmr = calculate_bmr_mifflin_st_jeor(weight_kg, height_cm, age, gender)
    if bmr <= 0:
        return 0.0
    try:
        af = float(activity_factor)
        if af <= 0 or math.isnan(af) or math.isinf(af):
            af = 1.375
    except (TypeError, ValueError):
        af = 1.375
    return round(bmr * af, 0)
