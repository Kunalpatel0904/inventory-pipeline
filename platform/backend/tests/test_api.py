import os

os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from fastapi.testclient import TestClient

from app.ai import analyze_deployment, deterministic_health_check, generate_infrastructure_config
from app.config import Settings
from app.llm import LLMProviderError, redact_sensitive
from app.main import app
from app.schemas import Autoscaling


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_and_ideas(client):
    health = client.get("/health")
    assert health.json() == {"status": "ok"}
    assert health.headers["x-content-type-options"] == "nosniff"
    response = client.get("/api/ideas")
    assert response.status_code == 200
    assert response.json() == []


def test_create_idea_and_validate_blank(client):
    response = client.post("/api/ideas", json={"content": "Improve preview environments"})
    assert response.status_code == 201
    assert response.json()["content"] == "Improve preview environments"
    assert client.post("/api/ideas", json={"content": " "}).status_code == 422


def test_ai_features_are_structured_and_safe(client):
    config = client.post("/api/ai/infrastructure-config", json={"requirement": "cost-sensitive staging"}).json()
    assert config["environment"] == "staging"
    assert config["replica_count"] == 1
    assert config["autoscaling"]["max_replicas"] <= 50
    analysis = client.post(
        "/api/ai/deployment-analysis",
        json={"logs": "database connection refused", "pod_status": []},
    ).json()
    assert analysis["status"] == "FAILED"
    assert analysis["recommendations"]


def test_failure_signatures_and_deterministic_health_gate():
    analysis = analyze_deployment("ImagePullBackOff", [{"reason": "ImagePullBackOff"}])
    assert "image" in analysis.issue.lower()
    assert deterministic_health_check(200, "ready") is True
    assert deterministic_health_check(500, "ready") is False
    assert deterministic_health_check(200, "fatal database error") is False


def test_configured_provider_requires_credentials_and_redacts_logs():
    settings = Settings(ai_provider="openai_compatible", ai_api_key=None)
    with pytest.raises(LLMProviderError):
        generate_infrastructure_config("staging", settings)
    assert redact_sensitive("Authorization: Bearer abc password=secret") == (
        "Authorization: Bearer [REDACTED] password=[REDACTED]"
    )


def test_openai_compatible_response_is_schema_validated(monkeypatch):
    monkeypatch.setattr(
        "app.ai.request_json",
        lambda *_args: {
            "environment": "staging",
            "replica_count": 1,
            "cpu_request": "100m",
            "memory_request": "128Mi",
            "autoscaling": {
                "enabled": False,
                "min_replicas": 1,
                "max_replicas": 3,
                "cpu_target_percent": 80,
            },
        },
    )
    config = generate_infrastructure_config(
        "cost-sensitive staging",
        Settings(ai_provider="openai_compatible", ai_api_key="test-key"),
    )
    assert config.environment == "staging"


def test_autoscaling_bounds_reject_inverted_range():
    with pytest.raises(ValueError):
        Autoscaling(enabled=True, min_replicas=5, max_replicas=2, cpu_target_percent=70)
