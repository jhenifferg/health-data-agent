from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from api.schemas.datasets import (
    DatasetDetailResponse,
    DatasetUploadResponse,
    QueryRequest,
    QueryResponse,
)
from api.schemas.error import ErrorResponse
from services.exceptions import (
    AIUnavailableError,
    AgentExecutionError,
    DatasetNotFoundError,
    InvalidDatasetError,
    ProviderQuotaExhaustedError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    ProviderAuthError,
    ProviderNotConfiguredError,
    ProviderTimeoutError,
    QueryInvalidError,
    UnsupportedFileError,
    UploadTooLargeError,
)

router = APIRouter(prefix="/api/datasets")


@router.post(
    "",
    response_model=DatasetUploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def upload_dataset(request: Request, file: UploadFile = File(...)) -> DatasetUploadResponse:
    try:
        session = await request.app.state.dataset_service.upload(file)
        return request.app.state.dataset_service.metadata(session)
    except UnsupportedFileError as error:
        raise HTTPException(status_code=415, detail={"code": error.code, "message": str(error)}) from error
    except UploadTooLargeError as error:
        raise HTTPException(status_code=413, detail={"code": error.code, "message": str(error)}) from error
    except InvalidDatasetError as error:
        raise HTTPException(status_code=400, detail={"code": error.code, "message": str(error)}) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="Erro interno ao processar o dataset") from error


@router.get(
    "/{dataset_id}",
    response_model=DatasetDetailResponse,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def get_dataset(request: Request, dataset_id: UUID) -> DatasetDetailResponse:
    try:
        session = request.app.state.registry.get(dataset_id)
        return request.app.state.dataset_service.metadata(session)
    except DatasetNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail={"code": error.code, "message": "Dataset não encontrado"},
        ) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="Erro interno ao ler o dataset") from error


@router.post(
    "/{dataset_id}/query",
    response_model=QueryResponse,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def query_dataset(
    request: Request,
    dataset_id: UUID,
    payload: QueryRequest,
) -> QueryResponse:
    if not payload.question.strip():
        raise HTTPException(status_code=422, detail="A pergunta não pode ser vazia")
    try:
        result = request.app.state.query_service.query(dataset_id, payload.question.strip())
        return QueryResponse(answer=result.answer, data=result.data)
    except DatasetNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail={"code": error.code, "message": "Dataset não encontrado"},
        ) from error
    except AIUnavailableError as error:
        raise HTTPException(status_code=503, detail={"code": error.code, "message": str(error)}) from error
    except ProviderRateLimitError as error:
        raise HTTPException(
            status_code=429,
            detail={"code": error.code, "message": str(error), "details": error.details()},
        ) from error
    except ProviderQuotaExhaustedError as error:
        raise HTTPException(
            status_code=429,
            detail={"code": error.code, "message": str(error), "details": error.details()},
        ) from error
    except ProviderUnavailableError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": error.code, "message": str(error), "details": error.details()},
        ) from error
    except (ProviderAuthError, ProviderNotConfiguredError) as error:
        raise HTTPException(status_code=503, detail={"code": error.code, "message": str(error), "details": error.details()}) from error
    except ProviderTimeoutError as error:
        raise HTTPException(status_code=504, detail={"code": error.code, "message": str(error), "details": error.details()}) from error
    except QueryInvalidError as error:
        raise HTTPException(status_code=422, detail={"code": error.code, "message": str(error)}) from error
    except AgentExecutionError as error:
        raise HTTPException(status_code=502, detail={"code": error.code, "message": str(error)}) from error
