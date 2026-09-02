from datetime import datetime
from typing import Annotated, Any, Literal, Union
from uuid import UUID

from pydantic import BaseModel, Field


class DatasetSummary(BaseModel):
    """files/rows/columns are totals across the loaded CSV datasets."""

    files: int
    rows: int
    columns: int


class ColumnMetadata(BaseModel):
    name: str
    type: Literal["string", "number", "integer", "boolean", "datetime", "unknown"]


class DatasetMetadata(BaseModel):
    name: str
    rows: int
    columnCount: int
    columns: list[ColumnMetadata]


class DatasetResponse(BaseModel):
    datasetId: UUID
    status: Literal["ready"]
    createdAt: datetime
    summary: DatasetSummary
    datasets: list[DatasetMetadata]


class DatasetUploadResponse(DatasetResponse):
    pass


class DatasetDetailResponse(DatasetResponse):
    pass


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class CountData(BaseModel):
    type: Literal["count"]
    value: int


class TableData(BaseModel):
    type: Literal["table"]
    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool = False
    returnedRows: int


DataPayload = Annotated[Union[CountData, TableData], Field(discriminator="type")]


class QueryResponse(BaseModel):
    answer: str
    data: DataPayload | None = None
