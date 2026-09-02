from typing import Any

from pydantic import BaseModel


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorInfo
