"""
gunicorn.conf.py - Gunicorn server configuration.

Ensures the background keep-alive heartbeat starts cleanly inside each worker
process after fork, avoiding pre-fork thread inheritance issues.
"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', 5002)}"
workers = int(os.environ.get("WEB_CONCURRENCY", 1))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 120))


def post_worker_init(worker):
    """Start background keep-alive heartbeat after the worker process has forked."""
    try:
        from keep_alive import start_keep_alive
        start_keep_alive()
    except Exception as e:
        worker.log.error(f"[keep-alive] Failed to start in worker: {e}")
