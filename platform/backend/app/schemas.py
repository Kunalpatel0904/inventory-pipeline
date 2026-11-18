from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IdeaCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class IdeaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    created_at: datetime


class InfrastructureRequest(BaseModel):
    requirement: str = Field(min_length=3, max_length=2000)


class Autoscaling(BaseModel):
    enabled: bool
    min_replicas: int = Field(ge=1, le=20)
    max_replicas: int = Field(ge=1, le=50)
    cpu_target_percent: int = Field(ge=10, le=95)

    @model_validator(mode="after")
    def validate_range(self) -> "Autoscaling":
        if self.max_replicas < self.min_replicas:
            raise ValueError("max_replicas must be greater than or equal to min_replicas")
        return self


class InfrastructureConfig(BaseModel):
    environment: str = Field(pattern=r"^(development|staging|production)$")
    replica_count: int = Field(ge=1, le=20)
    cpu_request: str = Field(pattern=r"^[0-9]+m$")
    memory_request: str = Field(pattern=r"^[0-9]+Mi$")
    autoscaling: Autoscaling


class DeploymentAnalysisRequest(BaseModel):
    logs: str = Field(min_length=1, max_length=100_000)
    pod_status: list[dict[str, str]] = Field(default_factory=list)


class DeploymentAnalysis(BaseModel):
    status: Literal["FAILED", "UNKNOWN"]
    issue: str
    possible_causes: list[str]
    recommendations: list[str]
