from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Iterator
from services.session_registry import SessionRegistry


@dataclass
class WorkspaceSession:
    workspace_id: UUID
    dataset_ids: list[UUID] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    name: str = ""


class WorkspaceRegistry:
    """Gerencia workspaces que agrupam múltiplos datasets."""

    def __init__(self):
        self._workspaces: dict[UUID, WorkspaceSession] = {}

    def create(self, name: str = "") -> WorkspaceSession:
        """Cria um novo workspace vazio."""
        workspace = WorkspaceSession(
            workspace_id=uuid4(),
            dataset_ids=[],
            name=name or "Workspace sem nome",
        )
        self._workspaces[workspace.workspace_id] = workspace
        return workspace

    def get(self, workspace_id: UUID) -> WorkspaceSession:
        """Retorna um workspace pelo ID."""
        if workspace_id not in self._workspaces:
            raise KeyError(f"Workspace {workspace_id} não encontrado")
        return self._workspaces[workspace_id]

    def add_dataset(self, workspace_id: UUID, dataset_id: UUID) -> WorkspaceSession:
        """Adiciona um dataset ao workspace."""
        workspace = self.get(workspace_id)
        if dataset_id not in workspace.dataset_ids:
            workspace.dataset_ids.append(dataset_id)
        return workspace

    def remove_dataset(self, workspace_id: UUID, dataset_id: UUID) -> WorkspaceSession:
        """Remove um dataset do workspace."""
        workspace = self.get(workspace_id)
        if dataset_id in workspace.dataset_ids:
            workspace.dataset_ids.remove(dataset_id)
        return workspace

    def delete(self, workspace_id: UUID) -> None:
        """Remove um workspace."""
        self._workspaces.pop(workspace_id, None)

    def __iter__(self) -> Iterator[WorkspaceSession]:
        """Itera sobre todos os workspaces."""
        return iter(self._workspaces.values())
