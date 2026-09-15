from pathlib import Path
import csv
from typing import Optional

import pandas as pd

from pipeline.csv_loader import CSVLoader
from pipeline.data_dictionary import DataDictionary
from pipeline.validator import DataValidator
from pipeline.zip_handler import ZipHandler
from services.config import MAX_QUERY_RESULT_ROWS


class DataManager:
    """Gerencia os datasets carregados e executa consultas."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.datasets: dict[str, pd.DataFrame] = {}
        self.dictionary: dict = {}
        self.provided_descriptions: dict[tuple[str, str], str] = {}

    def load(self, source_path: Optional[str] = None):
        if source_path:
            path = Path(source_path)

            if path.suffix.lower() == ".zip":
                ZipHandler.extract(str(path), str(self.data_dir))
                self.datasets = CSVLoader.load_directory(str(self.data_dir))

            elif path.suffix.lower() == ".csv":
                self.datasets = {
                    path.stem.lower(): CSVLoader.load_csv(str(path))
                }

            elif path.is_dir():
                self.datasets = CSVLoader.load_directory(str(path))

            else:
                raise ValueError(
                    f"Formato de origem nao suportado: {source_path}"
                )

        else:
            self.datasets = CSVLoader.load_directory(str(self.data_dir))

        DataValidator.validate_datasets(self.datasets)
        self.provided_descriptions = self._load_provided_dictionary()
        self.dictionary = DataDictionary.build(self.datasets, self.provided_descriptions)

        return self.datasets

    def _load_provided_dictionary(self) -> dict[tuple[str, str], str]:
        """Lê o dicionário opcional fornecido no ZIP sem tratá-lo como dataset."""
        candidates = [
            path
            for path in self.data_dir.rglob("*.csv")
            if path.stem.lower() in CSVLoader.DICTIONARY_FILENAMES
        ]
        if not candidates:
            return {}

        descriptions: dict[tuple[str, str], str] = {}
        with candidates[0].open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            required = {"arquivo", "coluna", "descricao"}
            if not reader.fieldnames or not required.issubset(
                {field.strip().lower() for field in reader.fieldnames}
            ):
                raise ValueError(
                    "O dicionário deve conter as colunas arquivo, coluna e descricao"
                )
            fields = {field.strip().lower(): field for field in reader.fieldnames}
            for row in reader:
                dataset = Path(row[fields["arquivo"]].strip()).stem.lower()
                column = row[fields["coluna"]].strip()
                description = row[fields["descricao"]].strip()
                if dataset and column and description:
                    descriptions[(dataset, column)] = description
        return descriptions

    def describe(self) -> dict:
        """Retorna metadata dos datasets disponíveis."""

        if not self.dictionary:
            self.load()

        return self.dictionary

    def planner_context(self) -> dict[str, dict]:
        """Metadados usados pelo planner para gerar o plano de consulta."""
        if not self.dictionary:
            self.load()

        context = {}

        for dataset, metadata in self.dictionary.items():
            descriptions = {
                column: description
                for column, description in metadata.get("descriptions", {}).items()
                if str(description).strip()
            }

            context[dataset] = {
                "columns": list(metadata.get("columns", [])),
                "types": metadata.get("dtypes", {}),
                "descriptions": descriptions,
                "sample": metadata.get("sample", [])[:3],
                "categorical_values": metadata.get("categorical_values", {}),
                "relationships": self._relationship_candidates(dataset),
            }

        return context

    def _relationship_candidates(self, dataset: str) -> list[dict]:
        """Infer likely joins from value overlap, without domain-specific names."""
        source = self.datasets[dataset]
        candidates: list[tuple[float, dict]] = []

        for other_name, target in self.datasets.items():
            if other_name == dataset:
                continue
            for left_column in source.columns:
                left = source[left_column].dropna().astype(str).head(5000)
                left_values = set(left)
                if not left_values:
                    continue
                left_unique_ratio = len(left_values) / len(left)

                for right_column in target.columns:
                    right = target[right_column].dropna().astype(str).head(5000)
                    right_values = set(right)
                    if not right_values:
                        continue
                    right_unique_ratio = len(right_values) / len(right)
                    if max(left_unique_ratio, right_unique_ratio) < 0.8:
                        continue

                    overlap = len(left_values & right_values)
                    coverage = overlap / min(len(left_values), len(right_values))
                    if overlap < 2 or coverage < 0.5:
                        continue

                    candidates.append(
                        (
                            coverage,
                            {
                                "dataset": other_name,
                                "left_column": left_column,
                                "right_column": right_column,
                                "overlap": round(coverage, 3),
                            },
                        )
                    )

        candidates.sort(key=lambda item: item[0], reverse=True)
        return [candidate for _, candidate in candidates[:10]]

    def query(
        self,
        operation: str,
        dataset: str,
        periodo: Optional[str] = None,
        group_by: Optional[str] = None,
        metric: Optional[str] = None,
        aggregation: Optional[str] = None,
        sort: Optional[str] = None,
        sort_direction: Optional[str] = None,
        limit: Optional[int] = None,
        filters: Optional[list[dict]] = None,
        filter_column: Optional[str] = None,
        filter_operator: Optional[str] = None,
        filter_value: Optional[str] = None,
        join_dataset: Optional[str] = None,
        join_left_on: Optional[str] = None,
        join_right_on: Optional[str] = None,
        join_how: Optional[str] = "inner",
        distinct_column: Optional[str] = None,
    ):
        if not self.datasets:
            self.load()

        if dataset not in self.datasets:
            raise ValueError(
                f"Dataset '{dataset}' nao encontrado. "
                f"Datasets disponiveis: {list(self.datasets.keys())}"
            )

        df = self.datasets[dataset].copy()

        # ---------------------------------------------------------
        # JOIN ENTRE DATASETS
        # ---------------------------------------------------------

        if join_dataset:
            if join_dataset not in self.datasets:
                raise ValueError(
                    f"Dataset de join '{join_dataset}' nao encontrado. "
                    f"Datasets disponiveis: {list(self.datasets.keys())}"
                )

            if not join_left_on or not join_right_on:
                raise ValueError(
                    "Para realizar join informe 'join_left_on' e 'join_right_on'."
                )

            if join_left_on not in df.columns:
                raise ValueError(
                    f"Coluna '{join_left_on}' nao encontrada no dataset '{dataset}'."
                )

            right_df = self.datasets[join_dataset].copy()

            if join_right_on not in right_df.columns:
                raise ValueError(
                    f"Coluna '{join_right_on}' nao encontrada no dataset "
                    f"'{join_dataset}'."
                )

            allowed_join_types = {"inner", "left", "right", "outer"}

            if join_how not in allowed_join_types:
                raise ValueError(
                    "join_how deve ser: inner, left, right ou outer."
                )

            df = df.merge(
                right_df,
                left_on=join_left_on,
                right_on=join_right_on,
                how=join_how,
                suffixes=("", f"_{join_dataset}"),
            )

        effective_filters = list(filters or [])

        # Compatibilidade com consultas antigas que ainda usam filter_column.
        if filter_column:
            effective_filters.append(
                {
                    "column": filter_column,
                    "operator": filter_operator,
                    "value": filter_value,
                }
            )

        for current_filter in effective_filters:
            filter_column = current_filter.get("column")
            filter_operator = current_filter.get("operator")
            filter_value = current_filter.get("value")
            if filter_column not in df.columns:
                raise ValueError(
                    f"Coluna de filtro '{filter_column}' nao encontrada "
                    f"no dataset '{dataset}'. "
                    f"Colunas disponiveis: {list(df.columns)}"
                )

            if not filter_operator:
                raise ValueError("filter_operator é obrigatório quando filter_column é informado")

            if filter_value is None:
                raise ValueError("filter_value é obrigatório quando filter_column é informado")

            operator = filter_operator.lower().strip()
            series = df[filter_column]

            if operator in {"gt", "gte", "lt", "lte"}:
                numeric_series = _to_numeric(series)
                numeric_value = pd.to_numeric(filter_value, errors="coerce")

                if pd.isna(numeric_value):
                    raise ValueError(
                        f"O valor '{filter_value}' não é numérico para o operador '{operator}'"
                    )

                if operator == "gt":
                    df = df[numeric_series > numeric_value]
                elif operator == "gte":
                    df = df[numeric_series >= numeric_value]
                elif operator == "lt":
                    df = df[numeric_series < numeric_value]
                elif operator == "lte":
                    df = df[numeric_series <= numeric_value]

            elif operator == "eq":
                df = df[series.astype(str).str.casefold() == str(filter_value).casefold()]

            elif operator == "ne":
                df = df[series.astype(str).str.casefold() != str(filter_value).casefold()]

            elif operator == "contains":
                df = df[
                    series.astype(str).str.contains(
                        str(filter_value),
                        case=False,
                        na=False,
                        regex=False,
                    )
                ]

            else:
                raise ValueError(f"Operador de filtro não suportado: {filter_operator}")

        if limit is not None:
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
                raise ValueError("limit deve ser um inteiro positivo")
            if limit > MAX_QUERY_RESULT_ROWS:
                raise ValueError(
                    f"limit excede o máximo seguro de {MAX_QUERY_RESULT_ROWS}"
                )

        if sort_direction is not None:
            normalized_direction = str(sort_direction).strip().lower()
            if normalized_direction not in {"asc", "desc"}:
                raise ValueError("sort_direction deve ser 'asc' ou 'desc'")
        else:
            normalized_direction = "desc"

        # ---------------------------------------------------------
        # FILTRO POR PERIODO
        # ---------------------------------------------------------

        if periodo:
            if "periodo" not in df.columns:
                if str(periodo).strip().lower() in {"periodo", "período", "period"}:
                    periodo = None
                else:
                    raise ValueError(
                        f"O dataset '{dataset}' nao possui a coluna 'periodo'. "
                        f"Colunas disponiveis: {list(df.columns)}"
                    )

            if periodo:
                df = df[df["periodo"].astype(str) == str(periodo)]

        normalized_operation = operation.lower().strip()

        # ---------------------------------------------------------
        # COUNT
        # ---------------------------------------------------------

        if normalized_operation in {"count", "contagem"}:

            if distinct_column:
                if distinct_column not in df.columns:
                    raise ValueError(
                        f"Coluna distinct_column '{distinct_column}' nao encontrada "
                        f"no dataset '{dataset}'. "
                        f"Colunas disponiveis: {list(df.columns)}"
                    )

                return {
                    "dataset": dataset,
                    "operation": "count",
                    "result": int(df[distinct_column].nunique()),
                    "distinct_column": distinct_column,
                }

            return {
                "dataset": dataset,
                "operation": "count",
                "result": int(len(df)),
            }

        # ---------------------------------------------------------
        # LIST
        # ---------------------------------------------------------

        if normalized_operation in {"list", "listar"}:
            effective_limit = limit if limit else 20
            if sort:
                if sort not in df.columns:
                    raise ValueError(
                        f"Coluna de ordenacao '{sort}' nao encontrada "
                        f"no dataset '{dataset}'. "
                        f"Colunas disponiveis: {list(df.columns)}"
                    )
                numeric_sort = _to_numeric(df[sort])
                if numeric_sort.notna().all():
                    df = df.assign(_sort_key=numeric_sort).sort_values(
                        by="_sort_key",
                        ascending=normalized_direction == "asc",
                        kind="stable",
                    ).drop(columns="_sort_key")
                else:
                    df = df.sort_values(
                        by=sort,
                        ascending=normalized_direction == "asc",
                        key=lambda values: values.astype("string").str.casefold(),
                        kind="stable",
                    )
            rows = df.head(effective_limit).to_dict(
                orient="records"
            )

            return {
                "dataset": dataset,
                "operation": "list",
                "result": rows,
                "truncated": len(df) > len(rows),
                "returned_rows": len(rows),
            }

        # ---------------------------------------------------------
        # AGGREGATE
        # ---------------------------------------------------------

        if normalized_operation in {
            "aggregate",
            "agregacao",
            "groupby",
            "agrupamento",
        }:

            if not metric:
                raise ValueError(
                    "Para agregacao informe 'metric'."
                )

            if not aggregation:
                raise ValueError(
                    "Para agregacao informe 'aggregation'."
                )

            if group_by and group_by not in df.columns:
                raise ValueError(
                    f"Coluna group_by '{group_by}' nao encontrada "
                    f"no dataset '{dataset}'. "
                    f"Colunas disponiveis: {list(df.columns)}"
                )

            if metric not in df.columns:
                raise ValueError(
                    f"Coluna metric '{metric}' nao encontrada "
                    f"no dataset '{dataset}'. "
                    f"Colunas disponiveis: {list(df.columns)}"
                )

            aggregation_map = {
                "avg": "mean",
                "sum": "sum",
                "count": "count",
                "min": "min",
                "max": "max",
            }

            aggregation = aggregation_map.get(aggregation.lower(), aggregation.lower())

            if aggregation not in aggregation_map.values():
                raise ValueError(
                    f"Agregacao '{aggregation}' nao suportada. "
                    f"Use: {', '.join(aggregation_map)}"
                )

            if aggregation == "count":
                if distinct_column:
                    if distinct_column not in df.columns:
                        raise ValueError(
                            f"Coluna distinct_column '{distinct_column}' nao encontrada "
                            f"no dataset '{dataset}'. "
                            f"Colunas disponiveis: {list(df.columns)}"
                        )

                    df["_metric"] = df[distinct_column]
                else:
                    df["_metric"] = df[metric]
            else:
                metric_values = _to_numeric(df[metric])

                if not metric_values.notna().any():
                    raise ValueError(
                        f"A métrica '{metric}' não possui valores numéricos válidos."
                    )

                df["_metric"] = metric_values

            # Valores ausentes não entram na agregação.
            df = df[df["_metric"].notna()]

            # Em um ranking de maior/menor valor, o corte unitário deve
            # ordenar pela métrica, mesmo que o LLM tenha escolhido a dimensão.
            if group_by and limit == 1 and aggregation in {"max", "min"}:
                sort = metric
                normalized_direction = "desc" if aggregation == "max" else "asc"

            if group_by:
                if aggregation == "count" and distinct_column:
                    grouped = (
                        df.groupby(group_by, dropna=False)["_metric"]
                        .nunique()
                        .reset_index()
                        .rename(columns={"_metric": metric})
                    )
                else:
                    grouped = (
                        df.groupby(group_by, dropna=False)["_metric"]
                        .agg(aggregation)
                        .reset_index()
                        .rename(columns={"_metric": metric})
                    )

                # Evita duas colunas com o mesmo nome quando
                # group_by e metric são a mesma coluna.
                if group_by == metric:
                    metric = f"{metric}_count"
                    grouped.columns = [group_by, metric]

            else:
                grouped = pd.DataFrame(
                    [{metric: df["_metric"].agg(aggregation)}]
                )

            # Se estamos contando a própria coluna agrupada,
            # ordenamos pela contagem, não pelo nome da dimensão.
            if aggregation == "count" and sort in {group_by, "count"}:
                sort = metric

            # -----------------------------------------------------
            # ORDENAÇÃO
            # -----------------------------------------------------

            if sort:
                if sort not in grouped.columns:
                    raise ValueError(
                        f"Coluna de ordenacao '{sort}' nao encontrada "
                        f"no resultado. "
                        f"Colunas disponiveis: {list(grouped.columns)}"
                    )

                grouped = grouped.sort_values(
                    by=sort,
                    ascending=normalized_direction == "asc",
                )

            # -----------------------------------------------------
            # LIMIT
            # -----------------------------------------------------

            total_rows = len(grouped)
            if limit is not None:
                grouped = grouped.head(limit)

            return {
                "dataset": dataset,
                "operation": "aggregate",
                "result": grouped.to_dict(
                    orient="records"
                ),
                "truncated": total_rows > len(grouped),
                "returned_rows": len(grouped),
            }

        # ---------------------------------------------------------
        # OPERAÇÃO INVÁLIDA
        # ---------------------------------------------------------

        raise ValueError(
            f"Operacao '{operation}' nao suportada. "
            f"Operacoes disponiveis: count, list, aggregate."
        )


def _to_numeric(values: pd.Series) -> pd.Series:
    """Converte decimais comuns, incluindo o formato brasileiro, para número."""
    normalized = values.astype("string").str.strip().str.replace("R$", "", regex=False)
    brazilian = normalized.str.contains(",", na=False)
    normalized.loc[brazilian] = (
        normalized.loc[brazilian]
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(normalized, errors="coerce")
