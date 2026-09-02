import unicodedata
from typing import Optional, Literal

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

from pipeline.data_manager import DataManager
from services.config import MAX_QUERY_RESULT_ROWS


class QueryFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: str = Field(
        description="Nome EXATO da coluna usada no filtro."
    )

    operator: Literal[
        "eq", "ne", "gt", "gte", "lt", "lte", "contains"
    ] = Field(
        description="Operador aplicado ao filtro."
    )

    value: str = Field(
        description="Valor utilizado no filtro."
    )

class DataQuery(BaseModel):
    operation: Literal[
        "count",
        "aggregate",
        "list"
    ] = Field(
        description=(
            "Tipo de operação a realizar sobre os dados. "
            "Use count para contar registros, list para listar registros "
            "e aggregate para calcular agregações."
        )
    )

    dataset: str = Field(
        description=(
            "Nome EXATO de um dos datasets retornados por describe_data. "
            "Nunca invente ou altere o nome."
        )
    )

    periodo: Optional[str] = Field(
        default=None,
        description=(
            "Período para filtrar os dados, somente quando o dataset "
            "possuir uma coluna 'periodo'."
        )
    )

    group_by: Optional[str] = Field(
        default=None,
        description=(
            "Nome EXATO da coluna usada para agrupamento. "
            "Deve existir no dataset."
        )
    )

    metric: Optional[str] = Field(
        default=None,
        description=(
            "Nome EXATO da coluna usada como métrica numérica. "
            "Deve existir no dataset."
        )
    )

    aggregation: Optional[
        Literal["sum", "avg", "count", "min", "max"]
    ] = Field(
        default=None,
        description=(
            "Operação matemática aplicada à métrica: "
            "sum, avg, count, min ou max."
        )
    )

    sort: Optional[str] = Field(
        default=None,
        description=(
            "Nome EXATO da coluna pela qual os resultados serão "
            "ordenados."
        )
    )

    sort_direction: Optional[Literal["asc", "desc"]] = Field(
        default=None,
        description=(
            "Direção da ordenação: asc para menores primeiro ou desc para "
            "maiores primeiro. Use junto com sort."
        ),
    )

    limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=MAX_QUERY_RESULT_ROWS,
        description=(
            "Número máximo de resultados a retornar. O limite público é "
            f"{MAX_QUERY_RESULT_ROWS}."
        )
    )
    
    filters: list[QueryFilter] = Field(
        default_factory=list,
        description=(
            "Lista de filtros aplicados à consulta. "
            "Use múltiplos itens quando a pergunta exigir mais de uma condição."
        )
    )

    filter_column: Optional[str] = Field(
        default=None,
        description="Nome EXATO da coluna usada para filtrar os dados."
    )

    filter_operator: Optional[
        Literal["eq", "ne", "gt", "gte", "lt", "lte", "contains"]
    ] = Field(
        default=None,
        description="Operador do filtro."
    )

    filter_value: Optional[str] = Field(
        default=None,
        description="Valor utilizado no filtro."
    )

    join_dataset: Optional[str] = Field(
        default=None,
        description="Nome EXATO do segundo dataset usado no join."
    )

    join_left_on: Optional[str] = Field(
        default=None,
        description="Coluna EXATA do dataset principal usada no join."
    )

    join_right_on: Optional[str] = Field(
        default=None,
        description="Coluna EXATA do segundo dataset usada no join."
    )

    join_how: Optional[
        Literal["inner", "left", "right", "outer"]
    ] = Field(
        default="inner",
        description="Tipo de join entre os datasets."
    )

    distinct_column: Optional[str] = Field(
        default=None,
        description=(
            "Nome EXATO da coluna usada para contar valores únicos. "
            "Use quando a pergunta pedir quantidade de pacientes, entidades "
            "ou identificadores únicos."
        )
    )

    @field_validator("operation", mode="before")
    @classmethod
    def normalize_operation(cls, value: str) -> str:
        normalized = _normalize_term(value)
        return {
            "contagem": "count",
            "listar": "list",
            "listagem": "list",
            "agregacao": "aggregate",
            "agrupamento": "aggregate",
            "groupby": "aggregate",
        }.get(normalized, normalized)

    @field_validator("aggregation", mode="before")
    @classmethod
    def normalize_aggregation(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_term(value)
        return {
            "media": "avg",
            "media_aritmetica": "avg",
            "soma": "sum",
            "minimo": "min",
            "maximo": "max",
            "maior": "max",
            "maximum": "max",
            "menor": "min",
        }.get(normalized, normalized)

    @field_validator("limit", mode="before")
    @classmethod
    def normalize_limit(cls, value: int | str | None) -> int | None:
        if value is None:
            return value
        if isinstance(value, bool):
            raise ValueError("limit deve ser um inteiro positivo")
        if isinstance(value, int):
            return value
        return int(value)

    @field_validator("sort_direction", mode="before")
    @classmethod
    def normalize_sort_direction(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_term(value)
        return {
            "crescente": "asc",
            "ascending": "asc",
            "decrescente": "desc",
            "descending": "desc",
        }.get(normalized, normalized)

    @model_validator(mode="after")
    def validate_plan_shape(self):
        if self.operation == "aggregate" and (not self.metric or not self.aggregation):
            raise ValueError("aggregate exige metric e aggregation")
        if self.sort_direction and not self.sort:
            raise ValueError("sort_direction exige sort")
        return self


def _normalize_term(value: str) -> str:
    without_accents = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return without_accents.lower().strip().replace("-", "_").replace(" ", "_")


def query_data(query: DataQuery, manager: Optional[DataManager] = None):
    """
    Executa uma consulta estruturada nos dados carregados.
    """

    data_manager = manager or DataManager()
    # Alguns modelos confundem o nome de uma coluna de data com o valor do
    # filtro especial `periodo`. Se o dataset nao possui essa coluna, remover
    # apenas essa forma inequívoca de placeholder evita uma segunda geracao e
    # preserva a semantica de consultar todo o dataset.
    if query.periodo and query.dataset in data_manager.datasets:
        columns = data_manager.datasets[query.dataset].columns
        if "periodo" not in columns and query.periodo in columns:
            query = query.model_copy(update={"periodo": None})
    effective_limit = query.limit
    if query.operation in {"list", "aggregate"}:
        effective_limit = min(query.limit or MAX_QUERY_RESULT_ROWS, MAX_QUERY_RESULT_ROWS)

    return data_manager.query(
        operation=query.operation,
        dataset=query.dataset,
        periodo=query.periodo,
        group_by=query.group_by,
        metric=query.metric,
        aggregation=query.aggregation,
        sort=query.sort,
        sort_direction=query.sort_direction,
        limit=effective_limit,
        filters=[item.model_dump() for item in query.filters],
        filter_column=query.filter_column,
        filter_operator=query.filter_operator,
        filter_value=query.filter_value,
        join_dataset=query.join_dataset,
        join_left_on=query.join_left_on,
        join_right_on=query.join_right_on,
        join_how=query.join_how,
        distinct_column=query.distinct_column,
    )


def describe_data(manager: Optional[DataManager] = None):
    """
    Retorna os datasets disponíveis e seus metadados,
    incluindo colunas, tipos de dados e amostras.
    """

    return (manager or DataManager()).describe()
