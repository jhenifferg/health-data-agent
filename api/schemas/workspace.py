from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(default="", max_length=255)


class DatasetReference(BaseModel):
    datasetId: UUID
    name: str
    rows: int
    columns: int


class WorkspaceResponse(BaseModel):
    workspaceId: UUID
    name: str
    createdAt: datetime
    datasets: list[DatasetReference]
    summary: dict[str, int]


class WorkspaceQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class WorkspaceQueryResponse(BaseModel):
    answer: str
    data: dict | None = None
