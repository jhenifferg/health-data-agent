import pandas as pd

from pipeline.data_manager import DataManager


def test_planner_context_discovers_relationships_from_values(tmp_path):
    manager = DataManager(data_dir=str(tmp_path))
    manager.datasets = {
        "alpha": pd.DataFrame(
            {"record_key": ["a", "b", "c"], "label": ["x", "y", "z"]}
        ),
        "beta": pd.DataFrame(
            {"owner_ref": ["a", "a", "c"], "amount": [1, 2, 3]}
        ),
    }
    manager.dictionary = {
        name: {
            "columns": list(frame.columns),
            "dtypes": {column: str(dtype) for column, dtype in frame.dtypes.items()},
            "sample": frame.head(3).to_dict(orient="records"),
            "categorical_values": {},
            "descriptions": {},
        }
        for name, frame in manager.datasets.items()
    }

    relationships = manager.planner_context()["alpha"]["relationships"]

    assert {
        "dataset": "beta",
        "left_column": "record_key",
        "right_column": "owner_ref",
        "overlap": 1.0,
    } in relationships


def test_relationship_discovery_does_not_depend_on_healthcare_names(tmp_path):
    manager = DataManager(data_dir=str(tmp_path))
    manager.datasets = {
        "one": pd.DataFrame({"opaque_a": ["k1", "k2", "k3"]}),
        "two": pd.DataFrame({"opaque_b": ["k1", "k2", "k2"]}),
    }
    manager.dictionary = {
        name: {
            "columns": list(frame.columns),
            "dtypes": {column: str(dtype) for column, dtype in frame.dtypes.items()},
            "sample": [],
            "categorical_values": {},
            "descriptions": {},
        }
        for name, frame in manager.datasets.items()
    }

    candidate = manager.planner_context()["one"]["relationships"][0]

    assert candidate["dataset"] == "two"
    assert candidate["left_column"] == "opaque_a"
    assert candidate["right_column"] == "opaque_b"
