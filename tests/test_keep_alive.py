"""Unit tests for keep_alive.py heartbeat module."""
import os
from unittest.mock import patch, MagicMock
import urllib.error

import keep_alive


class TestKeepAliveConfig:
    def test_is_keep_alive_enabled_default(self, monkeypatch):
        monkeypatch.delenv("KEEP_ALIVE_ENABLED", raising=False)
        assert keep_alive.is_keep_alive_enabled() is True

    def test_is_keep_alive_enabled_disabled(self, monkeypatch):
        for val in ("false", "FALSE", "0", "no", "off"):
            monkeypatch.setenv("KEEP_ALIVE_ENABLED", val)
            assert keep_alive.is_keep_alive_enabled() is False

    def test_is_keep_alive_enabled_enabled(self, monkeypatch):
        for val in ("true", "TRUE", "1", "yes", "on"):
            monkeypatch.setenv("KEEP_ALIVE_ENABLED", val)
            assert keep_alive.is_keep_alive_enabled() is True

    def test_get_target_url_none_when_unset(self, monkeypatch):
        monkeypatch.delenv("KEEP_ALIVE_URL", raising=False)
        monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
        monkeypatch.delenv("RENDER_EXTERNAL_HOSTNAME", raising=False)
        monkeypatch.delenv("RENDER_SERVICE_NAME", raising=False)
        assert keep_alive.get_target_url() is None

    def test_get_target_url_from_keep_alive_url(self, monkeypatch):
        monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
        monkeypatch.delenv("RENDER_EXTERNAL_HOSTNAME", raising=False)
        monkeypatch.delenv("RENDER_SERVICE_NAME", raising=False)
        monkeypatch.setenv("KEEP_ALIVE_URL", "https://vitallog.example.com")
        assert keep_alive.get_target_url() == "https://vitallog.example.com/health"

    def test_get_target_url_preserves_existing_health(self, monkeypatch):
        monkeypatch.setenv("KEEP_ALIVE_URL", "https://vitallog.example.com/health")
        assert keep_alive.get_target_url() == "https://vitallog.example.com/health"

    def test_get_target_url_from_render_external_url(self, monkeypatch):
        monkeypatch.delenv("KEEP_ALIVE_URL", raising=False)
        monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://vitallog.onrender.com/")
        assert keep_alive.get_target_url() == "https://vitallog.onrender.com/health"

    def test_get_target_url_from_render_external_hostname(self, monkeypatch):
        monkeypatch.delenv("KEEP_ALIVE_URL", raising=False)
        monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
        monkeypatch.delenv("RENDER_SERVICE_NAME", raising=False)
        monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "vitallog-deploy.onrender.com")
        assert keep_alive.get_target_url() == "https://vitallog-deploy.onrender.com/health"

    def test_get_target_url_from_render_service_name(self, monkeypatch):
        monkeypatch.delenv("KEEP_ALIVE_URL", raising=False)
        monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
        monkeypatch.delenv("RENDER_EXTERNAL_HOSTNAME", raising=False)
        monkeypatch.setenv("RENDER_SERVICE_NAME", "vitallog")
        assert keep_alive.get_target_url() == "https://vitallog.onrender.com/health"

    def test_get_target_url_override_priority(self, monkeypatch):
        monkeypatch.setenv("KEEP_ALIVE_URL", "https://custom.example.com")
        monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://vitallog.onrender.com")
        assert keep_alive.get_target_url() == "https://custom.example.com/health"

    def test_get_interval_seconds_default(self, monkeypatch):
        monkeypatch.delenv("KEEP_ALIVE_INTERVAL_MINUTES", raising=False)
        assert keep_alive.get_interval_seconds() == 420.0

    def test_get_interval_seconds_custom(self, monkeypatch):
        monkeypatch.setenv("KEEP_ALIVE_INTERVAL_MINUTES", "5")
        assert keep_alive.get_interval_seconds() == 300.0

    def test_get_interval_seconds_floats(self, monkeypatch):
        monkeypatch.setenv("KEEP_ALIVE_INTERVAL_MINUTES", "0.5")
        assert keep_alive.get_interval_seconds() == 30.0

    def test_get_interval_seconds_rejects_ge_14(self, monkeypatch):
        for val in ("14", "15", "20"):
            monkeypatch.setenv("KEEP_ALIVE_INTERVAL_MINUTES", val)
            assert keep_alive.get_interval_seconds() == 420.0

    def test_get_interval_seconds_rejects_le_0_or_invalid(self, monkeypatch):
        for val in ("0", "-5", "invalid"):
            monkeypatch.setenv("KEEP_ALIVE_INTERVAL_MINUTES", val)
            assert keep_alive.get_interval_seconds() == 420.0


class TestKeepAlivePing:
    @patch("urllib.request.urlopen")
    def test_ping_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        assert keep_alive.ping("https://example.com/health") is True
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert "VitaLog-KeepAlive" in req.get_header("User-agent")

    @patch("urllib.request.urlopen")
    def test_ping_non_200(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.getcode.return_value = 500
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        assert keep_alive.ping("https://example.com/health") is False

    @patch("urllib.request.urlopen")
    def test_ping_http_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://example.com/health",
            code=503,
            msg="Service Unavailable",
            hdrs={},
            fp=None
        )
        assert keep_alive.ping("https://example.com/health") is False

    @patch("urllib.request.urlopen")
    def test_ping_url_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        assert keep_alive.ping("https://example.com/health") is False

    @patch("urllib.request.urlopen")
    def test_ping_generic_exception(self, mock_urlopen):
        mock_urlopen.side_effect = RuntimeError("Socket timeout")
        assert keep_alive.ping("https://example.com/health") is False


class TestStartKeepAlive:
    def test_start_keep_alive_inert_without_url(self, monkeypatch):
        monkeypatch.delenv("KEEP_ALIVE_URL", raising=False)
        monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
        monkeypatch.delenv("RENDER_EXTERNAL_HOSTNAME", raising=False)
        monkeypatch.delenv("RENDER_SERVICE_NAME", raising=False)
        monkeypatch.delenv("TESTING", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        assert keep_alive.start_keep_alive() is False

    def test_start_keep_alive_disabled_when_env_false(self, monkeypatch):
        monkeypatch.setenv("KEEP_ALIVE_ENABLED", "false")
        monkeypatch.setenv("KEEP_ALIVE_URL", "https://example.com")
        monkeypatch.delenv("TESTING", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        assert keep_alive.start_keep_alive() is False

    @patch("threading.Thread")
    def test_start_keep_alive_starts_daemon_thread(self, mock_thread_class, monkeypatch):
        monkeypatch.setenv("KEEP_ALIVE_URL", "https://example.com")
        monkeypatch.delenv("TESTING", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        # Reset module state
        keep_alive._started_pids.clear()

        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        result = keep_alive.start_keep_alive()
        assert result is True
        mock_thread_class.assert_called_once_with(
            target=keep_alive._keep_alive_loop,
            args=("https://example.com/health", 420.0, 15.0),
            name=f"render-keep-alive-{os.getpid()}",
            daemon=True
        )
        mock_thread.start.assert_called_once()

        # Calling again does not start a second thread (idempotent per pid)
        assert keep_alive.start_keep_alive() is False
        mock_thread.start.assert_called_once()
