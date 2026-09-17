"""API endpoint tests for Phase 1."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "JARVIS Civic"
    assert data["status"] == "operational"
    assert "disclaimer" in data
    assert "AI-assisted civic decision-support" in data["disclaimer"]


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "jarvis-civic"
    assert "disclaimer" in data
    assert "AI-assisted civic decision-support" in data["disclaimer"]
