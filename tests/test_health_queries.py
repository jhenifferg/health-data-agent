from pipeline.data_manager import DataManager
from services.query_service import QueryService


DATA_DIR = (
    "/Users/jheniffer/Desktop/cursos&projetos/"
    "testes_csv_doenças/health_pack_v1"
)


def test_female_patients_with_diabetes():
    manager = DataManager(data_dir=DATA_DIR)
    manager.load()

    result = manager.query(
        operation="count",
        dataset="patients",
        filters=[
            {"column": "gender", "operator": "eq", "value": "F"},
            {"column": "description", "operator": "eq", "value": "Diabetes"},
        ],
        join_dataset="conditions",
        join_left_on="id",
        join_right_on="patient",
        join_how="inner",
        distinct_column="id",
    )

    assert result["result"] == 32

def test_most_frequent_condition_by_occurrences():
    manager = DataManager(data_dir=DATA_DIR)
    manager.load()

    result = manager.query(
        operation="aggregate",
        dataset="conditions",
        group_by="description",
        metric="description",
        aggregation="count",
        sort="description",
        sort_direction="desc",
        limit=1,
    )


    row = result["result"][0]

    assert row["description"] == "Viral sinusitis (disorder)"
    assert row["description_count"] == 1248


def test_common_health_questions_are_deterministic():
    manager = DataManager(data_dir=DATA_DIR)
    manager.load()
    service = QueryService.__new__(QueryService)

    patients = service._try_deterministic_query(
        manager, "How many patients are in the dataset?"
    )
    conditions = service._try_deterministic_query(
        manager, "What are the 5 most frequent conditions?"
    )
    female_diabetes = service._try_deterministic_query(
        manager, "How many female patients have diabetes?"
    )
    salary = service._try_deterministic_query(
        manager, "What is the average salary of the patients?"
    )

    assert patients.data == {"type": "count", "value": 1171}
    assert [row["description_count"] for row in conditions.data["rows"]] == [
        1248,
        653,
        563,
        516,
        449,
    ]
    assert female_diabetes.data == {"type": "count", "value": 32}
    assert salary.data is None
    assert "do not contain a salary or income field" in salary.answer
