from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .ai import analyze_deployment, generate_infrastructure_config
from .config import get_settings
from .db import Base, engine, get_db
from .models import Idea
from .schemas import (
    DeploymentAnalysis,
    DeploymentAnalysisRequest,
    IdeaCreate,
    IdeaRead,
    InfrastructureConfig,
    InfrastructureRequest,
)
from .llm import LLMProviderError

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Halcer Idea Board API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok"}


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    return "# HELP idea_board_up Application availability.\n# TYPE idea_board_up gauge\nidea_board_up 1\n"


@app.get("/api/ideas", response_model=list[IdeaRead])
def list_ideas(db: Session = Depends(get_db)) -> list[Idea]:
    return list(db.scalars(select(Idea).order_by(Idea.created_at.desc(), Idea.id.desc())))


@app.post("/api/ideas", response_model=IdeaRead, status_code=status.HTTP_201_CREATED)
def create_idea(payload: IdeaCreate, db: Session = Depends(get_db)) -> Idea:
    idea = Idea(content=payload.content.strip())
    if not idea.content:
        raise HTTPException(status_code=422, detail="content must not be blank")
    db.add(idea)
    db.commit()
    db.refresh(idea)
    return idea


@app.post("/api/ai/infrastructure-config", response_model=InfrastructureConfig)
def infrastructure_config(payload: InfrastructureRequest) -> InfrastructureConfig:
    try:
        return generate_infrastructure_config(payload.requirement)
    except LLMProviderError as exc:
        raise HTTPException(status_code=502, detail="AI provider unavailable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="AI provider returned invalid configuration") from exc


@app.post("/api/ai/deployment-analysis", response_model=DeploymentAnalysis)
def deployment_analysis(payload: DeploymentAnalysisRequest) -> DeploymentAnalysis:
    try:
        return analyze_deployment(payload.logs, payload.pod_status)
    except LLMProviderError as exc:
        raise HTTPException(status_code=502, detail="AI provider unavailable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="AI provider returned invalid analysis") from exc
