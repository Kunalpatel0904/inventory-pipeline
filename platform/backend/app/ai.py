import json
import re

from .config import Settings, get_settings
from .llm import request_json
from .schemas import Autoscaling, DeploymentAnalysis, InfrastructureConfig


def _deterministic_infrastructure_config(requirement: str) -> InfrastructureConfig:
    text = requirement.lower()
    environment = "production" if "production" in text else "development" if "dev" in text else "staging"
    cost_sensitive = "cost" in text or "cheap" in text or "small" in text
    replicas = 1 if cost_sensitive else 2
    cpu = "100m" if cost_sensitive else "250m"
    memory = "128Mi" if cost_sensitive else "256Mi"
    return InfrastructureConfig(
        environment=environment,
        replica_count=replicas,
        cpu_request=cpu,
        memory_request=memory,
        autoscaling=Autoscaling(
            enabled=not cost_sensitive,
            min_replicas=1,
            max_replicas=3 if cost_sensitive else 10,
            cpu_target_percent=80,
        ),
    )


def generate_infrastructure_config(
    requirement: str, settings: Settings | None = None
) -> InfrastructureConfig:
    settings = settings or get_settings()
    if settings.ai_provider == "openai_compatible":
        result = request_json(
            "Return only JSON matching this schema. Use only development, staging, or production; "
            "keep all values within the schema bounds: "
            f"{json.dumps(InfrastructureConfig.model_json_schema())}",
            requirement,
            settings,
        )
        return InfrastructureConfig.model_validate(result)
    return _deterministic_infrastructure_config(requirement)


def _deterministic_deployment_analysis(logs: str, pod_status: list[dict[str, str]]) -> DeploymentAnalysis:
    text = logs.lower()
    if "connection refused" in text or "could not connect" in text:
        issue = "Database connection refused."
        causes = ["PostgreSQL is unreachable.", "The database hostname or port may be incorrect."]
        recommendations = ["Verify the database hostname and port.", "Check credentials.", "Verify network connectivity and database readiness."]
    elif "imagepullbackoff" in text or any(p.get("reason") == "ImagePullBackOff" for p in pod_status):
        issue = "The container image could not be pulled."
        causes = ["The image tag is unavailable.", "The registry credentials or permissions are invalid."]
        recommendations = ["Verify the image tag exists.", "Check registry authentication and workload identity permissions."]
    elif "readiness probe failed" in text or any(p.get("ready") == "false" for p in pod_status):
        issue = "The application did not become ready."
        causes = ["The readiness endpoint is failing.", "The application may still be starting or misconfigured."]
        recommendations = ["Inspect application logs.", "Verify readiness probe path and configuration.", "Check dependency health."]
    else:
        issue = "Deployment health checks failed without a recognized signature."
        causes = ["The service may have a configuration or runtime error."]
        recommendations = ["Inspect pod events and application logs.", "Re-run deterministic health checks before considering rollback."]
    return DeploymentAnalysis(status="FAILED", issue=issue, possible_causes=causes, recommendations=recommendations)


def analyze_deployment(
    logs: str, pod_status: list[dict[str, str]], settings: Settings | None = None
) -> DeploymentAnalysis:
    settings = settings or get_settings()
    if settings.ai_provider == "openai_compatible":
        result = request_json(
            "Analyze deployment evidence and return only JSON matching this schema. "
            "Do not recommend destructive actions without deterministic health-check evidence. "
            f"Schema: {json.dumps(DeploymentAnalysis.model_json_schema())}",
            f"Logs:\n{logs}\nPod status:\n{pod_status}",
            settings,
        )
        return DeploymentAnalysis.model_validate(result)
    return _deterministic_deployment_analysis(logs, pod_status)


def deterministic_health_check(status_code: int, logs: str) -> bool:
    return status_code == 200 and not re.search(r"\b(crashloopbackoff|failed|fatal)\b", logs, re.IGNORECASE)
