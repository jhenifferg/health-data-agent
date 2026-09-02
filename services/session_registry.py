from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Iterator
from uuid import UUID, uuid4

from pipeline.data_manager import DataManager
from services.exceptions import DatasetNotFoundError


@dataclass
class DatasetSession:
    dataset_id: UUID
    root_dir: Path
    manager: DataManager
    created_at: datetime


class SessionRegistry:
    """Registry efêmero: os datasets desaparecem quando o processo termina."""

    def __init__(self, root_dir: str = ".runtime/datasets"):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[UUID, DatasetSession] = {}

    def create(self) -> DatasetSession:
        dataset_id = uuid4()
        root_dir = self.root_dir / str(dataset_id)
        data_dir = root_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=False)
        session = DatasetSession(
            dataset_id=dataset_id,
            root_dir=root_dir,
            manager=DataManager(data_dir=str(data_dir)),
            created_at=datetime.now(timezone.utc),
        )
        return session

    def register(self, session: DatasetSession) -> None:
        self._sessions[session.dataset_id] = session

    def discard(self, session: DatasetSession) -> None:
        self._sessions.pop(session.dataset_id, None)
        shutil.rmtree(session.root_dir, ignore_errors=True)

    def get(self, dataset_id: UUID) -> DatasetSession:
        try:
            return self._sessions[dataset_id]
        except KeyError as error:
            raise DatasetNotFoundError(str(dataset_id)) from error

    def remove(self, dataset_id: UUID) -> None:
        session = self._sessions.pop(dataset_id, None)
        if session:
            shutil.rmtree(session.root_dir, ignore_errors=True)

    def __iter__(self) -> Iterator[DatasetSession]:
        return iter(self._sessions.values())
