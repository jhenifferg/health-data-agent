from pipeline.data_manager import DataManager


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