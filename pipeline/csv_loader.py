from pathlib import Path

import pandas as pd

from tools.csv_tools import CSVTools


class CSVLoader:
    """Responsavel por carregar um ou mais CSVs para DataFrames padronizados."""

    DICTIONARY_FILENAMES = {"dicionario", "data_dictionary", "dictionary"}

    @staticmethod
    def load_csv(file_path: str) -> pd.DataFrame:
        return CSVTools.load_csv(file_path)

    @classmethod
    def load_directory(cls, directory: str) -> dict[str, pd.DataFrame]:
        base_path = Path(directory)
        if not base_path.exists():
            raise FileNotFoundError(f"Diretorio nao encontrado: {directory}")

        datasets: dict[str, pd.DataFrame] = {}
        for csv_file in base_path.rglob("*.csv"):
            if csv_file.is_symlink():
                raise ValueError(f"Link simbólico não permitido: {csv_file}")
            dataset_name = csv_file.stem.lower()
            if dataset_name in cls.DICTIONARY_FILENAMES:
                continue
            if dataset_name in datasets:
                raise ValueError(
                    f"Datasets com o mesmo nome encontrados: {dataset_name}"
                )
            datasets[dataset_name] = cls.load_csv(str(csv_file))

        return datasets
