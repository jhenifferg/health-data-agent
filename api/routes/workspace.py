from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from api.schemas.workspace import (
    DatasetReference,
    WorkspaceCreateRequest,
    WorkspaceQueryRequest,
    WorkspaceQueryResponse,
    WorkspaceResponse,
)
from api.schemas.error import ErrorResponse
from services.exceptions import (
    DatasetNotFoundError,
    QueryInvalidError,
    ProviderRateLimitError,
    ProviderQuotaExhaustedError,
    ProviderUnavailableError,
    ProviderAuthError,
    ProviderNotConfiguredError,
    ProviderTimeoutError,
    AgentExecutionError,
    AIUnavailableError,
)

router = APIRouter(prefix="/api/workspaces")


@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_workspace(request: Request, payload: WorkspaceCreateRequest) -> WorkspaceResponse:
    try:
        workspace = request.app.state.workspace_registry.create(name=payload.name)
        return WorkspaceResponse(
            workspaceId=workspace.workspace_id,
            name=workspace.name,
            createdAt=workspace.created_at,
            datasets=[],
            summary={"files": 0, "rows": 0, "columns": 0},
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail="Erro ao criar workspace") from error


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def get_workspace(request: Request, workspace_id: UUID) -> WorkspaceResponse:
    try:
        workspace = request.app.state.workspace_registry.get(workspace_id)
        datasets: list[DatasetReference] = []
        total_rows = 0
        total_columns = 0

        for dataset_id in workspace.dataset_ids:
            try:
                session = request.app.state.registry.get(dataset_id)
                metadata = request.app.state.dataset_service.metadata(session)
                total_rows += metadata["summary"]["rows"]
                total_columns += metadata["summary"]["columns"]
                datasets.append(
                    DatasetReference(
                        datasetId=dataset_id,
                        name=metadata["datasets"][0]["name"] if metadata["datasets"] else "unknown",
                        rows=metadata["summary"]["rows"],
                        columns=metadata["summary"]["columns"],
                    )
                )
            except DatasetNotFoundError:
                pass

        return WorkspaceResponse(
            workspaceId=workspace.workspace_id,
            name=workspace.name,
            createdAt=workspace.created_at,
            datasets=datasets,
            summary={"files": len(datasets), "rows": total_rows, "columns": total_columns},
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Workspace não encontrado") from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="Erro ao ler workspace") from error


@router.post(
    "/{workspace_id}/datasets/{dataset_id}",
    response_model=WorkspaceResponse,
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def add_dataset_to_workspace(
    request: Request, workspace_id: UUID, dataset_id: UUID
) -> WorkspaceResponse:
    try:
        workspace = request.app.state.workspace_registry.add_dataset(workspace_id, dataset_id)
        session = request.app.state.registry.get(dataset_id)
        datasets: list[DatasetReference] = []
        total_rows = 0
        total_columns = 0

        for did in workspace.dataset_ids:
            try:
                s = request.app.state.registry.get(did)
                metadata = request.app.state.dataset_service.metadata(s)
                total_rows += metadata["summary"]["rows"]
                total_columns += metadata["summary"]["columns"]
                datasets.append(
                    DatasetReference(
                        datasetId=did,
                        name=metadata["datasets"][0]["name"] if metadata["datasets"] else "unknown",
                        rows=metadata["summary"]["rows"],
                        columns=metadata["summary"]["columns"],
                    )
                )
            except DatasetNotFoundError:
                pass

        return WorkspaceResponse(
            workspaceId=workspace.workspace_id,
            name=workspace.name,
            createdAt=workspace.created_at,
            datasets=datasets,
            summary={"files": len(datasets), "rows": total_rows, "columns": total_columns},
        )
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail="Dataset não encontrado") from error
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Workspace não encontrado") from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="Erro ao adicionar dataset") from error


@router.delete(
    "/{workspace_id}/datasets/{dataset_id}",
    response_model=WorkspaceResponse,
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def remove_dataset_from_workspace(
    request: Request, workspace_id: UUID, dataset_id: UUID
) -> WorkspaceResponse:
    try:
        workspace = request.app.state.workspace_registry.remove_dataset(workspace_id, dataset_id)
        datasets: list[DatasetReference] = []
        total_rows = 0
        total_columns = 0

        for did in workspace.dataset_ids:
            try:
                s = request.app.state.registry.get(did)
                metadata = request.app.state.dataset_service.metadata(s)
                total_rows += metadata["summary"]["rows"]
                total_columns += metadata["summary"]["columns"]
                datasets.append(
                    DatasetReference(
                        datasetId=did,
                        name=metadata["datasets"][0]["name"] if metadata["datasets"] else "unknown",
                        rows=metadata["summary"]["rows"],
                        columns=metadata["summary"]["columns"],
                    )
                )
            except DatasetNotFoundError:
                pass

        return WorkspaceResponse(
            workspaceId=workspace.workspace_id,
            name=workspace.name,
            createdAt=workspace.created_at,
            datasets=datasets,
            summary={"files": len(datasets), "rows": total_rows, "columns": total_columns},
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Workspace não encontrado") from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="Erro ao remover dataset") from error


@router.post(
    "/{workspace_id}/query",
    response_model=WorkspaceQueryResponse,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def query_workspace(
    request: Request,
    workspace_id: UUID,
    payload: WorkspaceQueryRequest,
) -> WorkspaceQueryResponse:
    if not payload.question.strip():
        raise HTTPException(status_code=422, detail="A pergunta não pode ser vazia")
    try:
        workspace = request.app.state.workspace_registry.get(workspace_id)
        if not workspace.dataset_ids:
            raise HTTPException(status_code=422, detail="Nenhum dataset adicionado ao workspace")

        result = request.app.state.query_service.query_workspace(
            workspace.dataset_ids, payload.question.strip()
        )
        return WorkspaceQueryResponse(answer=result.answer, data=result.data)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Workspace não encontrado") from error
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
    except Exception as error:
        raise HTTPException(status_code=500, detail="Erro ao processar consulta") from error
