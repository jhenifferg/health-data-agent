import json
from pathlib import Path

import pandas as pd


class DataDictionary:
    """Gera metadados de datasets para descoberta por agentes."""

    @staticmethod
    def build(
        datasets: dict[str, pd.DataFrame],
        descriptions: dict[tuple[str, str], str] | None = None,
    ) -> dict:
        dictionary: dict[str, dict] = {}
        descriptions = descriptions or {}

        for name, df in datasets.items():
            categorical_values = {}

            for column in df.columns:
                if (
                    pd.api.types.is_object_dtype(df[column])
                    or pd.api.types.is_string_dtype(df[column])
                    or isinstance(df[column].dtype, pd.CategoricalDtype)
                ):
                    unique_values = df[column].dropna().astype(str).unique()

                    # Só expõe valores quando a cardinalidade é razoável.
                    # Evita enviar IDs, textos livres e milhares de valores ao planner.
                    if len(unique_values) <= 200:
                        categorical_values[column] = unique_values.tolist()
            dictionary[name] = {
                "rows": int(len(df)),
                "columns": list(df.columns),
                "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
                "sample": df.head(3).to_dict(orient="records"),
                "categorical_values": categorical_values,
                "descriptions": {
                    column: descriptions[(name, column)]
                    for column in df.columns
                    if (name, column) in descriptions
                },
            }

        return dictionary

    @staticmethod
    def save(dictionary: dict, output_path: str) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump(dictionary, file, ensure_ascii=False, indent=2)
        return str(path)
