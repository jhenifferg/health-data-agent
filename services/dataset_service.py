from pathlib import Path
from typing import Any
from zipfile import BadZipFile

from fastapi import UploadFile

from pipeline.zip_handler import (
    UnsafeZipEntryError as PipelineUnsafeZipEntryError,
    ZipHandler,
    ZipLimitExceededError as PipelineZipLimitExceededError,
)
from services.config import (
    MAX_UPLOAD_BYTES,
    MAX_ZIP_MEMBER_BYTES,
    MAX_ZIP_MEMBERS,
    MAX_ZIP_UNCOMPRESSED_BYTES,
)
from services.exceptions import (
    InvalidDatasetError,
    InvalidZipError,
    NoCsvFilesFoundError,
    UnsafeZipEntryError,
    UnsupportedFileError,
    UploadTooLargeError,
    ZipLimitExceededError,
)
from services.session_registry import DatasetSession, SessionRegistry


class DatasetService:
    def __init__(self, registry: SessionRegistry):
        self.registry = registry

    async def upload(self, file: UploadFile) -> DatasetSession:
        filename = file.filename or ""
        suffix = Path(filename).suffix.lower()
        if suffix not in {".zip", ".csv"}:
            raise UnsupportedFileError("Apenas arquivos .zip ou .csv são aceitos")

        session = self.registry.create()
        safe_filename = Path(filename.replace("\\", "/")).name or f"upload{suffix}"
        upload_path = session.root_dir / safe_filename
        try:
            total_bytes = 0
            with upload_path.open("wb") as output:
                while chunk := await file.read(1024 * 1024):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_UPLOAD_BYTES:
                        raise UploadTooLargeError(
                            "O upload excede o tamanho máximo permitido"
                        )
                    output.write(chunk)

            if suffix == ".zip":
                extracted = ZipHandler.extract(
                    str(upload_path),
                    str(session.manager.data_dir),
                    max_members=MAX_ZIP_MEMBERS,
                    max_member_bytes=MAX_ZIP_MEMBER_BYTES,
                    max_uncompressed_bytes=MAX_ZIP_UNCOMPRESSED_BYTES,
                )
                if not any(Path(path).suffix.lower() == ".csv" for path in extracted):
                    raise NoCsvFilesFoundError("Nenhum arquivo CSV foi encontrado no ZIP")
                session.manager.load(str(session.manager.data_dir))
            else:
                session.manager.load(str(upload_path))

            if not session.manager.datasets:
                raise NoCsvFilesFoundError("Nenhum arquivo CSV foi encontrado")
            self.registry.register(session)
            return session
        except UploadTooLargeError:
            self.registry.discard(session)
            raise
        except PipelineUnsafeZipEntryError as error:
            self.registry.discard(session)
            raise UnsafeZipEntryError(str(error)) from error
        except PipelineZipLimitExceededError as error:
            self.registry.discard(session)
            raise ZipLimitExceededError(str(error)) from error
        except BadZipFile as error:
            self.registry.discard(session)
            raise InvalidZipError("O arquivo ZIP é inválido ou está corrompido") from error
        except NoCsvFilesFoundError:
            self.registry.discard(session)
            raise
        except (OSError, ValueError) as error:
            self.registry.discard(session)
            raise InvalidDatasetError(f"Não foi possível processar o dataset: {error}") from error
        finally:
            await file.close()

    @staticmethod
    def metadata(session: DatasetSession) -> dict[str, Any]:
        dictionary = session.manager.describe()
        datasets = [
            {
                "name": name,
                "rows": info["rows"],
                "columnCount": len(info["columns"]),
                "columns": [
                    {"name": column, "type": _public_type(info["dtypes"].get(column))}
                    for column in info["columns"]
                ],
            }
            for name, info in dictionary.items()
        ]
        return {
            "datasetId": str(session.dataset_id),
            "status": "ready",
            "createdAt": session.created_at,
            "summary": {
                "files": len(datasets),
                "rows": sum(item["rows"] for item in datasets),
                "columns": sum(len(item["columns"]) for item in datasets),
            },
            "datasets": datasets,
        }


def _public_type(dtype: str | None) -> str:
    normalized = (dtype or "").lower()
    if "datetime" in normalized or "date" in normalized:
        return "datetime"
    if "bool" in normalized:
        return "boolean"
    if "int" in normalized:
        return "integer"
    if "float" in normalized or "double" in normalized:
        return "number"
    if normalized in {"object", "string", "str"}:
        return "string"
    return "unknown"
