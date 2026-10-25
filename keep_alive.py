"""
keep_alive.py - Background self-ping heartbeat for Render free tier web services.

Pings the public /health endpoint every 10 minutes so Render does not spin down
idle services after 15 minutes of inactivity.
"""
import os
import time
import threading
import urllib.request
import urllib.error

_lock = threading.Lock()
_started = False


def is_keep_alive_enabled() -> bool:
    """Check if the keep-alive heartbeat is enabled."""
    val = os.environ.get("KEEP_ALIVE_ENABLED", "true").strip().lower()
    return val not in ("false", "0", "no", "off")


def get_target_url() -> str | None:
    """Resolve the public /health URL from environment variables.

    Priority:
    1. KEEP_ALIVE_URL (manual override)
    2. RENDER_EXTERNAL_URL (automatically populated by Render)
    """
    base = os.environ.get("KEEP_ALIVE_URL") or os.environ.get("RENDER_EXTERNAL_URL")
    if not base:
        return None

    cleaned = base.strip().rstrip("/")
    if not cleaned:
        return None

    if not cleaned.endswith("/health"):
        return f"{cleaned}/health"
    return cleaned


def get_interval_seconds() -> float:
    """Return the ping interval in seconds.

    Defaults to 10 minutes (600 seconds).
    Maximum allowed interval is under 14 minutes to prevent Render free-tier sleep.
    """
    raw = os.environ.get("KEEP_ALIVE_INTERVAL_MINUTES")
    default_minutes = 10.0

    if raw:
        try:
            val = float(raw.strip())
            # Guard: interval must be positive and strictly under 14 minutes
            if 0 < val < 14.0:
                return val * 60.0
            print(f"[keep-alive] Invalid interval {val}m (must be > 0 and < 14m). Using default 10m.")
        except ValueError:
            print(f"[keep-alive] Failed to parse KEEP_ALIVE_INTERVAL_MINUTES={raw}. Using default 10m.")

    return default_minutes * 60.0


def ping(url: str, timeout: float = 10.0) -> bool:
    """Send an HTTP GET request to the target URL."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "VitaLog-KeepAlive/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.getcode()
            if status == 200:
                return True
            print(f"[keep-alive] Ping returned non-200 status {status} for {url}")
            return False
    except urllib.error.HTTPError as e:
        print(f"[keep-alive] Ping HTTP error {e.code} for {url}: {e.reason}")
        return False
    except urllib.error.URLError as e:
        print(f"[keep-alive] Ping URL error for {url}: {e.reason}")
        return False
    except Exception as e:
        print(f"[keep-alive] Ping failed for {url}: {e}")
        return False


def _keep_alive_loop(url: str, interval_seconds: float):
    """Loop running in a daemon thread, periodically pinging the public URL."""
    # Initial sleep to ensure server is fully bound and accepting requests
    time.sleep(interval_seconds)

    while True:
        ping(url)
        time.sleep(interval_seconds)


def start_keep_alive(app=None) -> bool:
    """Start the background keep-alive heartbeat if configured.

    Safe and non-blocking:
    - Inert if neither KEEP_ALIVE_URL nor RENDER_EXTERNAL_URL is set.
    - Disabled when KEEP_ALIVE_ENABLED=false.
    - Disabled during automated test runs (TESTING or pytest).
    - Prevents duplicate threads during Werkzeug hot reloading.
    """
    global _started

    # Skip in automated test environments
    if os.environ.get("TESTING") or os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    if app and getattr(app, "testing", False):
        return False

    # Skip in Werkzeug reloader master process
    if app and getattr(app, "debug", False) and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return False

    if not is_keep_alive_enabled():
        return False

    url = get_target_url()
    if not url:
        return False

    with _lock:
        if _started:
            return False
        _started = True

    interval = get_interval_seconds()
    thread = threading.Thread(
        target=_keep_alive_loop,
        args=(url, interval),
        name="render-keep-alive",
        daemon=True
    )
    thread.start()
    print(f"[keep-alive] Started heartbeat targeting {url} every {interval / 60:.1f}m")
    return True
