import pandas as pd

from tools.csv_tools import CSVTools


def test_repeated_text_is_loaded_as_category(tmp_path):
    path = tmp_path / "arbitrary.csv"
    pd.DataFrame(
        {
            "opaque_key": [f"key-{index}" for index in range(200)],
            "repeated_value": ["alpha", "beta"] * 100,
        }
    ).to_csv(path, index=False)

    dataframe = CSVTools.load_csv(str(path))

    assert str(dataframe["repeated_value"].dtype) == "category"
    assert dataframe["repeated_value"].astype(str).tolist()[:2] == ["alpha", "beta"]
    assert str(dataframe["opaque_key"].dtype) == "string"
