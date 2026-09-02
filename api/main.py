import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes.datasets import router as datasets_router
from api.routes.health import router as health_router
from api.routes.workspace import router as workspace_router
from api.schemas.error import ErrorResponse
from services.dataset_service import DatasetService
from services.query_service import QueryService
from services.session_registry import SessionRegistry
from services.workspace_registry import WorkspaceRegistry


def create_app(runtime_root: str | None = None) -> FastAPI:
    app = FastAPI(title="Data Assistant API", version="0.1.0")
    origins = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    registry = SessionRegistry(
        runtime_root or os.getenv("RUNTIME_ROOT", ".runtime/datasets")
    )
    app.state.registry = registry
    app.state.dataset_service = DatasetService(registry)
    app.state.query_service = QueryService(registry)
    app.state.workspace_registry = WorkspaceRegistry()

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        code_by_status = {
            400: "invalid_request",
            500: "internal_error",
            404: "not_found",
            415: "unsupported_file_type",
            422: "validation_error",
            502: "query_execution_error",
            503: "ai_provider_unavailable",
        }
        detail = exc.detail
        if isinstance(detail, dict):
            code = detail.get("code", "http_error")
            message = detail.get("message", "Requisição inválida")
            details = detail.get("details")
        else:
            code = code_by_status.get(exc.status_code, "http_error")
            message = detail if isinstance(detail, str) else "Requisição inválida"
            details = None
        response = ErrorResponse(
            error={
                "code": code,
                "message": message,
                "details": details,
            }
        )
        return JSONResponse(status_code=exc.status_code, content=response.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        response = ErrorResponse(
            error={
                "code": "validation_error",
                "message": "A requisição contém dados inválidos",
                "details": exc.errors(),
            }
        )
        return JSONResponse(status_code=422, content=response.model_dump(mode="json"))

    app.include_router(health_router)
    app.include_router(datasets_router)
    app.include_router(workspace_router)
    return app


app = create_app()
