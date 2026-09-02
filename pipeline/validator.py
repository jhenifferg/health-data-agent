import pandas as pd


class DataValidator:
    """Valida datasets carregados no pipeline."""

    @staticmethod
    def validate_dataframe(df: pd.DataFrame, dataset_name: str = "dataset") -> None:
        if df.empty:
            raise ValueError(f"Dataset vazio: {dataset_name}")

        duplicated_columns = df.columns[df.columns.duplicated()].tolist()
        if duplicated_columns:
            raise ValueError(
                f"Dataset {dataset_name} possui colunas duplicadas: {duplicated_columns}"
            )

    @classmethod
    def validate_datasets(cls, datasets: dict[str, pd.DataFrame]) -> None:
        if not datasets:
            raise ValueError("Nenhum dataset carregado no pipeline")

        for name, df in datasets.items():
            cls.validate_dataframe(df, dataset_name=name)