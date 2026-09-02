from uuid import uuid4

from pipeline.data_manager import DataManager
from services.query_service import QueryService


DATA_DIR = (
    "/Users/jheniffer/Desktop/cursos&projetos/"
    "testes_csv_doenças/health_pack_v1"
)


class FakeSession:
    def __init__(self, manager):
        self.manager = manager


class FakeRegistry:
    def __init__(self, session):
        self.session = session

    def get(self, dataset_id):
        return self.session


def build_service():
    manager = DataManager(data_dir=DATA_DIR)
    manager.load()

    return QueryService(
        FakeRegistry(
            FakeSession(manager)
        )
    )