"""
keep_alive.py - Background self-ping heartbeat for Render free tier web services.

Pings the public /health endpoint periodically so Render does not spin down
idle services after 15 minutes of inactivity.
"""
import os
import time
import threading
import urllib.request
import urllib.error

_lock = threading.Lock()
_started_pids: set[int] = set()


def is_keep_alive_enabled() -> bool:
    """Check if the keep-alive heartbeat is enabled."""
    val = os.environ.get("KEEP_ALIVE_ENABLED", "true").strip().lower()
    return val not in ("false", "0", "no", "off")


def get_target_url() -> str | None:
    """Resolve the public /health URL from environment variables.

    Priority:
    1. KEEP_ALIVE_URL (manual override)
    2. RENDER_EXTERNAL_URL (automatically populated by Render for web services)
    3. RENDER_EXTERNAL_HOSTNAME (automatically populated hostname e.g. myapp.onrender.com)
    4. RENDER_SERVICE_NAME (service name e.g. vitallog -> https://vitallog.onrender.com)
    """
    base = (
        os.environ.get("KEEP_ALIVE_URL")
        or os.environ.get("RENDER_EXTERNAL_URL")
        or (f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}" if os.environ.get("RENDER_EXTERNAL_HOSTNAME") else None)
        or (f"https://{os.environ.get('RENDER_SERVICE_NAME')}.onrender.com" if os.environ.get("RENDER_SERVICE_NAME") else None)
    )
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

    Defaults to 7 minutes (420 seconds) to ensure multiple pings occur within
    Render's 15-minute idle spin-down window.
    Maximum allowed interval is strictly under 14 minutes.
    """
    raw = os.environ.get("KEEP_ALIVE_INTERVAL_MINUTES")
    default_minutes = 7.0

    if raw:
        try:
            val = float(raw.strip())
            # Guard: interval must be positive and strictly under 14 minutes
            if 0 < val < 14.0:
                return val * 60.0
            print(f"[keep-alive] Invalid interval {val}m (must be > 0 and < 14m). Using default 7m.")
        except ValueError:
            print(f"[keep-alive] Failed to parse KEEP_ALIVE_INTERVAL_MINUTES={raw}. Using default 7m.")

    return default_minutes * 60.0


def ping(url: str, timeout: float = 10.0) -> bool:
    """Send an HTTP GET request to the target URL with standard browser headers."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 (VitaLog-KeepAlive)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    req = urllib.request.Request(url, headers=headers)
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


def _keep_alive_loop(url: str, interval_seconds: float, initial_delay_seconds: float = 15.0):
    """Loop running in a daemon thread, periodically pinging the public URL."""
    # Brief initial pause to allow the web server to bind ports and start serving
    time.sleep(initial_delay_seconds)

    while True:
        success = ping(url)
        # If ping fails (e.g. transient network glitch), retry sooner (30s) instead of waiting full interval
        sleep_duration = interval_seconds if success else min(30.0, interval_seconds)
        time.sleep(sleep_duration)


def start_keep_alive(app=None, initial_delay_seconds: float | None = None) -> bool:
    """Start the background keep-alive heartbeat if configured.

    Safe and non-blocking:
    - Inert if neither KEEP_ALIVE_URL nor RENDER_EXTERNAL_URL/RENDER_EXTERNAL_HOSTNAME is set.
    - Disabled when KEEP_ALIVE_ENABLED=false.
    - Disabled during automated test runs (TESTING or pytest).
    - Prevents duplicate threads during Werkzeug hot reloading and per-process tracking.
    """
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

    current_pid = os.getpid()
    with _lock:
        if current_pid in _started_pids:
            return False
        _started_pids.add(current_pid)

    if initial_delay_seconds is None:
        raw_delay = os.environ.get("KEEP_ALIVE_INITIAL_DELAY_SECONDS")
        if raw_delay:
            try:
                initial_delay_seconds = float(raw_delay)
            except ValueError:
                initial_delay_seconds = 15.0
        else:
            initial_delay_seconds = 15.0

    interval = get_interval_seconds()
    thread = threading.Thread(
        target=_keep_alive_loop,
        args=(url, interval, initial_delay_seconds),
        name=f"render-keep-alive-{current_pid}",
        daemon=True
    )
    thread.start()
    print(f"[keep-alive] Started heartbeat targeting {url} every {interval / 60:.1f}m (pid {current_pid})")
    return True
