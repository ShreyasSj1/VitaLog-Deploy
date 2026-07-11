import json
import pytest
from tests.conftest import make_user, login

class TestPWARoutes:
    def test_service_worker_route(self, client):
        resp = client.get("/service-worker.js")
        assert resp.status_code == 200
        assert resp.headers["Content-Type"] == "application/javascript"
        assert resp.headers["Service-Worker-Allowed"] == "/"
        assert b"vitallog-cache-v1" in resp.data

    def test_manifest_route(self, client):
        resp = client.get("/manifest.json")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["short_name"] == "VitalLog"
        assert data["display"] == "standalone"
        assert len(data["icons"]) == 2

    def test_offline_route(self, client):
        resp = client.get("/offline")
        assert resp.status_code == 200
        assert b"You are currently offline" in resp.data
