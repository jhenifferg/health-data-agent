from fastapi import APIRouter

from api.schemas.health import HealthResponse
from services.config import is_ai_configured

router = APIRouter()


@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return {"status": "ok", "aiConfigured": is_ai_configured()}
