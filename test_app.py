import pytest

from app import app


@pytest.fixture
def client():
    return app.test_client()


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_health_redis_down(client, monkeypatch):
    monkeypatch.setenv("REDIS_PORT", "6390")
    assert client.get("/health").status_code == 503


def test_visits_increments(client):
    first = client.get("/visits").get_json()["visits"]
    second = client.get("/visits").get_json()["visits"]
    assert second == first + 1


def test_metrics_exposes_counter_and_version(client):
    client.get("/health")
    body = client.get("/metrics").get_data(as_text=True)
    assert 'endpoint="/health"' in body
    assert "app_version_info" in body
