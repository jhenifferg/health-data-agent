import json
import logging
import math
import re
import time
from datetime import datetime, timezone
from uuid import uuid4
from dataclasses import dataclass
from typing import Any
from uuid import UUID
import httpx

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from agents.csv_agent import build_tools, create_agent
from agents.prompts import SYSTEM_PROMPT
from agents.prompts import GROQ_PLANNER_PROMPT
from services.config import (
    AGENT_REQUEST_TIMEOUT_SECONDS,
    AI_PROVIDER,
    GEMINI_MODEL,
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_MAX_CONCURRENT_REQUESTS,
    GROQ_MAX_COMPLETION_TOKENS,
    PROVIDER_COOLDOWN_SECONDS,
    is_ai_configured,
)
from services.json_safe import to_json_safe
from services.exceptions import (
    AIUnavailableError,
    AgentExecutionError,
    AgentIterationLimitError,
    AgentTimeoutError,
    ProviderError,
    ProviderQuotaExhaustedError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    ProviderNotConfiguredError,
    ProviderAuthError,
    ProviderTimeoutError,
    QueryInvalidError,
    ToolExecutionError,
    UnknownToolError,
)
from services.session_registry import SessionRegistry
from services.provider_health import ProviderHealth
from tools.data_tools import DataQuery

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    answer: str
    data: dict[str, Any] | None
    telemetry: dict[str, Any] | None = None


class QueryService:
    def __init__(
        self,
        registry: SessionRegistry,
        max_iterations: int | None = None,
        provider_health: ProviderHealth | None = None,
    ):
        self.registry = registry
        from services.config import MAX_AGENT_ITERATIONS

        self.max_iterations = max_iterations or MAX_AGENT_ITERATIONS
        self.provider_health = provider_health or ProviderHealth(
            max_concurrent_requests=GROQ_MAX_CONCURRENT_REQUESTS
        )

    def query(self, dataset_id: UUID, question: str) -> QueryResult:
        session = self.registry.get(dataset_id)
        if not is_ai_configured():
            raise AIUnavailableError("O provedor de IA não está configurado")

        return self._execute_query(session.manager, question, dataset_id)

    def query_workspace(self, dataset_ids: list[UUID], question: str) -> QueryResult:
        """Executa uma query sobre múltiplos datasets agregados."""
        if not is_ai_configured():
            raise AIUnavailableError("O provedor de IA não está configurado")

        from pipeline.data_manager import DataManager
        import tempfile
        from pathlib import Path

        # Cria um DataManager agregado com dados de todos os datasets
        with tempfile.TemporaryDirectory() as temp_dir:
            aggregated_manager = DataManager(data_dir=str(temp_dir))
            aggregated_manager.datasets = {}
            aggregated_manager.dictionary = {}
            aggregated_manager.provided_descriptions = {}

            # Carrega dados de todos os datasets
            for dataset_id in dataset_ids:
                try:
                    session = self.registry.get(dataset_id)
                    # Merge datasets
                    aggregated_manager.datasets.update(session.manager.datasets)
                    aggregated_manager.dictionary.update(session.manager.dictionary)
                    aggregated_manager.provided_descriptions.update(
                        session.manager.provided_descriptions
                    )
                except Exception as e:
                    logger.warning(f"Falha ao carregar dataset {dataset_id}: {e}")

            # Executa a query com o DataManager agregado
            return self._execute_query(aggregated_manager, question, dataset_ids[0])

    def _execute_query(self, manager: Any, question: str, dataset_id: UUID) -> QueryResult:
        """Executa a query usando o DataManager fornecido."""
        if not is_ai_configured():
            raise AIUnavailableError("O provedor de IA não está configurado")

        query_id = f"q-{uuid4()}"
        logger.info("agent query started dataset_id=%s query_id=%s", dataset_id, query_id)
        try:
            messages = []
            last_tool_result: dict[str, Any] | None = None
            fallback_used = False
            provider = AI_PROVIDER
            agent = None
            telemetry = {
                "query_id": query_id,
                "provider_calls": 0,
                "groq_calls": 0,
                "gemini_calls": 0,
                "input_tokens_total": None,
                "output_tokens_total": None,
                "total_tokens": None,
                "fallback_count": 0,
                "tools_called": [],
                "latency_total_ms": 0,
                "model": self._model(provider),
                "request_sent": False,
                "block_source": None,
                "status": None,
            }

            tools = self._build_tools(manager, provider)
            tool_map = {tool.name: tool for tool in tools}
            messages = self._messages(manager, question, provider)

            if self.provider_health.remaining(provider, self._model(provider)):
                self._log_local_block(query_id, provider)
                if provider != "groq" and self._fallback_available():
                    provider = "groq"
                    fallback_used = True
                    telemetry["fallback_count"] += 1
                    telemetry["model"] = self._model(provider)
                else:
                    source = (
                        "circuit_breaker"
                        if self.provider_health.state(provider, self._model(provider))
                        == ProviderHealth.OPEN
                        else "cooldown"
                    )
                    raise self._cooldown_error(provider, source=source)

            try:
                if fallback_used:
                    tools = self._build_tools(manager, provider)
                    tool_map = {tool.name: tool for tool in tools}
                    messages = self._messages(manager, question, provider)
                    agent = create_agent(manager, tools=tools, provider=provider)
                else:
                    agent = create_agent(manager, tools=tools)
            except Exception as error:
                provider_error = self._provider_error(error, provider)
                if provider_error:
                    self._record_provider_failure(provider, provider_error)
                if not self._fallback_available() or provider == "groq":
                    raise provider_error or error
                logger.warning(
                    "primary AI provider unavailable during startup; switching to groq"
                )
                self._ensure_provider_available("groq")
                provider = "groq"
                telemetry["fallback_count"] += 1
                telemetry["model"] = self._model(provider)
                tools = self._build_tools(manager, provider)
                tool_map = {tool.name: tool for tool in tools}
                messages = self._messages(manager, question, provider)
                agent = create_agent(manager, tools=tools, provider=provider)
                fallback_used = True
            max_iterations = 1 if provider == "groq" else self.max_iterations
            for iteration in range(1, max_iterations + 1):
                logger.info("agent iteration=%d dataset_id=%s query_id=%s", iteration, dataset_id, query_id)
                started_at: float | None = None
                request_started_at: str | None = None
                reservation_id: str | None = None
                try:
                    estimated_tokens = self._estimate_messages(messages) if provider == "groq" else 0
                    reservation_id = self._ensure_provider_available(
                        provider, estimated_tokens, query_id
                    )
                    started_at = time.monotonic()
                    request_started_at = self._timestamp()
                    telemetry["request_sent"] = True
                    self._log_decision(
                        query_id,
                        provider,
                        "REQUEST_SENT",
                        provider_called=True,
                        request_started_at=request_started_at,
                    )
                    with self.provider_health.request(provider, self._model(provider)):
                        response = agent.invoke(messages)
                    raw_response = self._raw_response(response)
                    self.provider_health.mark_success(provider, self._model(provider))
                    telemetry["provider_calls"] += 1
                    telemetry[f"{provider}_calls"] += 1
                    latency_ms = round((time.monotonic() - started_at) * 1000)
                    telemetry["latency_total_ms"] += latency_ms
                    usage = self._usage(raw_response)
                    for key in ("input_tokens", "output_tokens", "total_tokens"):
                        if usage.get(key) is not None:
                            total_key = f"{key}_total" if key != "total_tokens" else key
                            telemetry[total_key] = (telemetry[total_key] or 0) + usage[key]
                    headers = self._provider_headers(raw_response)
                    self._update_budget(provider, raw_response)
                    self.provider_health.reconcile(
                        reservation_id,
                        actual_tokens=usage.get("total_tokens"),
                        authoritative_tokens="x-ratelimit-remaining-tokens" in headers,
                        authoritative_requests="x-ratelimit-remaining-requests" in headers,
                    )
                    reservation_id = None
                    self._apply_rate_telemetry(telemetry, headers)
                    telemetry["status"] = "success"
                    self._log_model_call(provider, raw_response, started_at, iteration, query_id)
                    self._log_decision(
                        query_id,
                        provider,
                        "HTTP_SUCCESS",
                        provider_called=True,
                        request_started_at=request_started_at,
                        request_finished_at=self._timestamp(),
                        headers=headers,
                    )
                except TimeoutError as error:
                    self.provider_health.reconcile(reservation_id, release=True)
                    if started_at is not None:
                        self._log_model_failure(provider, started_at, iteration, "timeout", None, query_id)
                    if (
                        provider != "groq"
                        and not fallback_used
                        and self._fallback_available()
                    ):
                        logger.warning(
                            "primary AI provider timed out; switching to groq"
                        )
                        failed_provider = provider
                        provider = "groq"
                        telemetry["fallback_count"] += 1
                        telemetry["model"] = self._model(provider)
                        tools = self._build_tools(manager, provider)
                        tool_map = {tool.name: tool for tool in tools}
                        agent = create_agent(
                            manager, tools=tools, provider="groq"
                        )
                        messages = self._messages(manager, question, provider)
                        last_tool_result = None
                        self.provider_health.cooldown(
                            failed_provider,
                            PROVIDER_COOLDOWN_SECONDS,
                            self._model(failed_provider),
                        )
                        fallback_used = True
                        continue
                    raise AgentTimeoutError("O provedor excedeu o tempo limite") from error
                except Exception as error:
                    headers = self._provider_headers(error)
                    self.provider_health.reconcile(
                        reservation_id,
                        release=True,
                        authoritative_tokens="x-ratelimit-remaining-tokens" in headers,
                        authoritative_requests="x-ratelimit-remaining-requests" in headers,
                    )
                    if started_at is not None:
                        self._log_model_failure(provider, started_at, iteration, "error", error, query_id)
                        decision = (
                            "HTTP_429_PROVIDER"
                            if self._status_code(error) == 429
                            else "HTTP_OTHER_ERROR"
                        )
                        telemetry["status"] = "rate_limit" if decision == "HTTP_429_PROVIDER" else "error"
                        self._apply_rate_telemetry(telemetry, headers)
                        self._log_decision(
                            query_id,
                            provider,
                            decision,
                            provider_called=True,
                            request_started_at=request_started_at,
                            request_finished_at=self._timestamp(),
                            headers=headers,
                        )
                    logger.error("ERRO REAL DO PROVIDER: %r", error)
                    provider_error = self._provider_error(error, provider)
                    if provider_error:
                        self._record_provider_failure(provider, provider_error)
                    if (
                        provider_error
                        and provider != "groq"
                        and not fallback_used
                        and self._fallback_available()
                    ):
                        logger.warning(
                            "primary AI provider unavailable; switching to groq"
                        )
                        self._ensure_provider_available("groq")
                        provider = "groq"
                        telemetry["fallback_count"] += 1
                        telemetry["model"] = self._model(provider)
                        tools = self._build_tools(manager, provider)
                        tool_map = {tool.name: tool for tool in tools}
                        agent = create_agent(
                            manager, tools=tools, provider="groq"
                        )
                        messages = self._messages(manager, question, provider)
                        last_tool_result = None
                        fallback_used = True
                        continue
                    if provider_error:
                        raise provider_error from error
                    raise
                plan = self._structured_plan(response)
                if plan is not None:
                    plan = self._normalize_plan(plan, question, manager)
                    tool = tool_map.get("query_data")
                    if tool is None:
                        raise UnknownToolError("Ferramenta desconhecida: query_data")
                    try:
                        result = tool.invoke(plan.model_dump())
                    except Exception as error:
                        raise QueryInvalidError(
                            "O planner produziu uma DataQuery invalida"
                        ) from error
                    telemetry["tools_called"].append("query_data")
                    return QueryResult(
                        answer=self._answer_from_result(result),
                        data=self._result_as_data(result),
                        telemetry=telemetry,
                    )

                messages.append(response)
                tool_calls = getattr(response, "tool_calls", []) or []
                telemetry["tools_called"].extend(
                    call.get("name") for call in tool_calls if call.get("name")
                )
                if not tool_calls:
                    logger.info("agent query finished dataset_id=%s", dataset_id)
                    return QueryResult(
                        answer=self._content_as_text(response.content),
                        data=self._result_as_data(last_tool_result),
                        telemetry=telemetry,
                    )

                describes_first = any(
                    tool_call["name"] == "describe_data" for tool_call in tool_calls
                )
                for tool_call in tool_calls:
                    tool_name = tool_call["name"]
                    if tool_name not in tool_map:
                        raise UnknownToolError(f"Ferramenta desconhecida: {tool_name}")
                    if describes_first and tool_name != "describe_data":
                        described_datasets = set(last_tool_result or {})
                        requested_dataset = tool_call.get("args", {}).get("dataset")
                        if not fallback_used or requested_dataset not in described_datasets:
                            available = ", ".join(sorted(described_datasets))
                            content = (
                                "Consulta adiada: use o resultado de describe_data e "
                                "gere uma nova chamada com os nomes exatos do dataset "
                                "e das colunas. Datasets disponíveis: "
                                f"{available}"
                            )
                            messages.append(
                                ToolMessage(
                                    content=content,
                                    tool_call_id=tool_call["id"],
                                )
                            )
                            continue
                    logger.info("agent tool=%s dataset_id=%s", tool_name, dataset_id)
                    try:
                        result = tool_map[tool_name].invoke(tool_call.get("args", {}))
                    except Exception as error:
                        logger.warning(
                            "agent tool failed tool=%s args=%s error=%s",
                            tool_name,
                            tool_call.get("args", {}),
                            error,
                        )
                        raise QueryInvalidError(
                            f"Falha ao executar a ferramenta: {tool_name}"
                        ) from error
                    last_tool_result = result if isinstance(result, dict) else None
                    if tool_name == "query_data":
                        logger.info(
                            "query_result dataset_id=%s provider=%s rows=%s",
                            dataset_id,
                            provider,
                            result.get("returned_rows") if isinstance(result, dict) else None,
                        )
                        return QueryResult(
                            answer=self._answer_from_result(result),
                            data=self._result_as_data(last_tool_result),
                            telemetry=telemetry,
                        )
                    messages.append(
                        ToolMessage(
                            content=self._compact_tool_result(result),
                            tool_call_id=tool_call["id"],
                        )
                    )

            logger.warning("agent iteration limit dataset_id=%s", dataset_id)
            raise AgentIterationLimitError("O agente excedeu o limite de iterações")
        except (AIUnavailableError, AgentExecutionError):
            raise
        except Exception as error:
            logger.exception("agent query failed dataset_id=%s", dataset_id)
            raise AgentExecutionError("Falha ao executar a consulta") from error

    @staticmethod
    def _content_as_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in content
            )
        return str(content)

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _model(provider: str) -> str:
        return GROQ_MODEL if provider == "groq" else GEMINI_MODEL

    @staticmethod
    def _raw_response(response: Any) -> Any:
        if isinstance(response, dict) and "raw" in response:
            return response.get("raw") or response
        return response

    @staticmethod
    def _structured_plan(response: Any) -> DataQuery | None:
        if not isinstance(response, dict) or "parsed" not in response:
            return None
        parsing_error = response.get("parsing_error")
        if parsing_error is not None:
            raise QueryInvalidError("O provider retornou um schema invalido") from parsing_error
        parsed = response.get("parsed")
        if parsed is None:
            raise QueryInvalidError("O provider nao retornou uma DataQuery")
        try:
            if (
                isinstance(parsed, dict)
                and parsed.get("operation") == "aggregate"
                and parsed.get("aggregation") == "count"
                and parsed.get("group_by")
                and not parsed.get("metric")
            ):
                parsed["metric"] = parsed["group_by"]
            plan = parsed if isinstance(parsed, DataQuery) else DataQuery.model_validate(parsed)
        except ValueError as error:
            raise QueryInvalidError("O provider retornou uma DataQuery invalida") from error
        if (
            plan.operation == "aggregate"
            and plan.metric
            and plan.sort
            and plan.sort.lower() in {"sum", "avg", "count", "min", "max", "total"}
        ):
            plan = plan.model_copy(update={"sort": plan.metric})
        return plan

    @staticmethod
    def _normalize_plan(plan: DataQuery, question: str, manager: Any) -> DataQuery:
        normalized_question = question.lower()
        asks_record = any(
            term in normalized_question
            for term in ("registro", "linha", "lançamento", "lancamento")
        )
        if (
            asks_record
            and plan.operation == "aggregate"
            and plan.aggregation in {"max", "min"}
            and plan.metric
            and not plan.group_by
        ):
            return DataQuery(
                operation="list",
                dataset=plan.dataset,
                periodo=plan.periodo,
                sort=plan.metric,
                sort_direction="desc" if plan.aggregation == "max" else "asc",
                limit=1,
            )
        asks_supplier = any(
            term in normalized_question for term in ("fornecedor", "fornecedores")
        )
        asks_identifier = any(
            term in normalized_question for term in ("cpf", "cnpj", "documento")
        )
        asks_product = "produto" in normalized_question
        asks_product_identifier = any(
            term in normalized_question for term in ("numero do produto", "número do produto", "codigo", "código")
        )
        dataframe = getattr(manager, "datasets", {}).get(plan.dataset)
        columns = list(getattr(dataframe, "columns", []))
        if plan.join_dataset:
            datasets = getattr(manager, "datasets", {})
            main_dataframe = datasets.get(plan.dataset)
            join_dataframe = datasets.get(plan.join_dataset)

            if main_dataframe is not None and join_dataframe is not None:
                join_columns = list(join_dataframe.columns)

                def find_matching_column(
                    source_dataframe,
                    target_dataframe,
                    target_column,
                ):
                    if target_column not in target_dataframe.columns:
                        return None

                    target_values = set(
                        target_dataframe[target_column]
                        .dropna()
                        .astype(str)
                        .head(5000)
                    )

                    if not target_values:
                        return None

                    candidates = []

                    for column in source_dataframe.columns:
                        source_values = set(
                            source_dataframe[column]
                            .dropna()
                            .astype(str)
                            .head(5000)
                        )

                        if not source_values:
                            continue

                        overlap = len(source_values & target_values)
                        ratio = overlap / min(len(source_values), len(target_values))

                        if ratio >= 0.8:
                            candidates.append((ratio, column))

                    if not candidates:
                        return None

                    candidates.sort(reverse=True)

                    if (
                        len(candidates) > 1
                        and candidates[0][0] == candidates[1][0]
                    ):
                        return None

                    return candidates[0][1]

                if plan.join_left_on not in columns:
                    repaired = find_matching_column(
                        main_dataframe,
                        join_dataframe,
                        plan.join_right_on,
                    )

                    if repaired:
                        plan.join_left_on = repaired
                    else:
                        raise QueryInvalidError(
                            f"Join inválido: coluna '{plan.join_left_on}' não existe "
                            f"no dataset '{plan.dataset}'."
                        )

                if plan.join_right_on not in join_columns:
                    repaired = find_matching_column(
                        join_dataframe,
                        main_dataframe,
                        plan.join_left_on,
                    )

                    if repaired:
                        plan.join_right_on = repaired
                    else:
                        raise QueryInvalidError(
                            f"Join inválido: coluna '{plan.join_right_on}' não existe "
                            f"no dataset '{plan.join_dataset}'."
                        )

        # Prefere colunas legíveis para filtros textuais.
        if (
            plan.filter_operator == "contains"
            and plan.filter_column
            and plan.filter_value
        ):
            normalized_filter = plan.filter_column.lower()

            technical_names = ("code", "id", "uuid", "identifier")

            if any(name in normalized_filter for name in technical_names):
                readable_column = next(
                    (
                        column
                        for column in columns
                        if any(
                            name in column.lower()
                            for name in (
                                "description",
                                "descricao",
                                "name",
                                "nome",
                                "title",
                                "category",
                            )
                        )
                    ),
                    None,
                )

                if readable_column:
                    plan = plan.model_copy(
                        update={"filter_column": readable_column}
                    )

        asks_most_expensive = any(
            term in normalized_question
            for term in ("mais caro", "mais cara", "mais caros", "mais caras")
        )

        asks_total_cost = any(
            term in normalized_question
            for term in ("custo total", "preço total", "preco total", "valor total", "acumulado")
        )

        if (
            asks_most_expensive
            and not asks_total_cost
            and plan.operation == "list"
        ):
            unit_cost_column = next(
                (
                    column
                    for column in columns
                    if column.lower() in {
                        "base_cost",
                        "unit_cost",
                        "unit_price",
                        "price",
                        "preco_unitario",
                        "preço_unitário",
                    }
                ),
                None,
            )

            if unit_cost_column:
                plan = plan.model_copy(
                    update={
                        "metric": unit_cost_column,
                        "sort": unit_cost_column,
                        "sort_direction": "desc",
                    }
                )

        if not plan.group_by:
            return plan

        normalized_group = plan.group_by.lower()

        if asks_supplier and not asks_identifier and (
            "cpf" in normalized_group or "cnpj" in normalized_group
        ):
            readable_supplier = next(
                (
                    column
                    for column in columns
                    if "razao_social" in column.lower() and "emitente" in column.lower()
                ),
                None,
            )
            if readable_supplier:
                return plan.model_copy(update={"group_by": readable_supplier})
        if asks_product and not asks_product_identifier and (
            "numero" in normalized_group or "codigo" in normalized_group
        ):
            readable_product = next(
                (
                    column
                    for column in columns
                    if "descricao" in column.lower() and "produto" in column.lower()
                ),
                None,
            )
            if readable_product:
                return plan.model_copy(update={"group_by": readable_product})
        return plan

    def _log_local_block(self, query_id: str, provider: str) -> None:
        state = self.provider_health.state(provider, self._model(provider))
        if state == ProviderHealth.OPEN:
            decision, source = "LOCAL_CIRCUIT_OPEN", "circuit_breaker"
        else:
            decision, source = "LOCAL_COOLDOWN", "cooldown"
        self._log_decision(
            query_id,
            provider,
            decision,
            provider_called=False,
            block_source=source,
        )

    def _log_budget_block(
        self, query_id: str | None, provider: str, budget: dict
    ) -> None:
        self._log_decision(
            query_id,
            provider,
            "LOCAL_TOKEN_BUDGET_BLOCK",
            provider_called=False,
            block_source="local_budget",
            headers={
                "x-ratelimit-limit-tokens": budget.get("token_limit"),
                "x-ratelimit-remaining-tokens": budget.get("remaining_tokens"),
                "x-ratelimit-reset-tokens": budget.get("token_reset"),
                "x-ratelimit-limit-requests": budget.get("request_limit"),
                "x-ratelimit-remaining-requests": budget.get("remaining_requests"),
                "x-ratelimit-reset-requests": budget.get("request_reset"),
            },
        )

    @staticmethod
    def _log_decision(
        query_id: str | None,
        provider: str,
        decision: str,
        *,
        provider_called: bool,
        block_source: str | None = None,
        request_started_at: str | None = None,
        request_finished_at: str | None = None,
        headers: dict[str, Any] | None = None,
    ) -> None:
        headers = headers or {}
        logger.info(
            "provider_decision query_id=%s provider=%s model=%s decision=%s "
            "provider_called=%s provider_rate_limit_source=%s "
            "request_started_at=%s request_finished_at=%s "
            "tpm_limit=%s tpm_remaining=%s tpm_reset=%s "
            "requests_limit=%s requests_remaining=%s requests_reset=%s retry_after=%s",
            query_id,
            provider,
            QueryService._model(provider),
            decision,
            str(provider_called).lower(),
            block_source,
            request_started_at,
            request_finished_at,
            headers.get("x-ratelimit-limit-tokens"),
            headers.get("x-ratelimit-remaining-tokens"),
            headers.get("x-ratelimit-reset-tokens"),
            headers.get("x-ratelimit-limit-requests"),
            headers.get("x-ratelimit-remaining-requests"),
            headers.get("x-ratelimit-reset-requests"),
            headers.get("retry-after"),
        )

    @staticmethod
    def _apply_rate_telemetry(telemetry: dict[str, Any], headers: dict[str, str]) -> None:
        telemetry.update(
            {
                "tpm_limit": headers.get("x-ratelimit-limit-tokens"),
                "tpm_remaining": headers.get("x-ratelimit-remaining-tokens"),
                "tpm_reset": headers.get("x-ratelimit-reset-tokens"),
                "requests_limit": headers.get("x-ratelimit-limit-requests"),
                "requests_remaining": headers.get("x-ratelimit-remaining-requests"),
                "requests_reset": headers.get("x-ratelimit-reset-requests"),
                "retry_after": headers.get("retry-after"),
            }
        )

    def _fallback_available(self) -> bool:
        return (
            AI_PROVIDER != "groq"
            and bool(GROQ_API_KEY)
            and not self.provider_health.remaining("groq", GROQ_MODEL)
            and self.provider_health.state("groq", GROQ_MODEL) != ProviderHealth.OPEN
        )

    @staticmethod
    def _build_tools(manager: Any, provider: str):
        try:
            return build_tools(manager, provider=provider)
        except TypeError:
            # Mantem fakes e integracoes antigas que aceitam apenas manager.
            return build_tools(manager)

    @staticmethod

    def _relevant_categorical_values(
        planner_context: dict,
        question: str,
    ) -> dict:
        question_lower = question.casefold()

        for metadata in planner_context.values():
            categorical_values = metadata.get("categorical_values", {})

            for column, values in categorical_values.items():
                relevant = [
                    value
                    for value in values
                    if str(value).casefold() in question_lower
                    or any(
                        word in str(value).casefold()
                        for word in question_lower.split()
                        if len(word) >= 4
                    )
                ]

                metadata["categorical_values"][column] = relevant[:10]

        return planner_context

    @staticmethod
    def _messages(manager: Any, question: str, provider: str):
        try:
            planner_context = manager.planner_context()
            planner_context = QueryService._relevant_categorical_values(
            planner_context,
            question,
        )
        except (AttributeError, ValueError):
            planner_context = {}

        if provider == "groq":
            context = json.dumps(planner_context, ensure_ascii=False, separators=(",", ":"))
            return [
                SystemMessage(content=GROQ_PLANNER_PROMPT.format(context=context)),
                HumanMessage(content=question),
            ]

        dataset_summary = ""
        if planner_context:
            dataset_names = ", ".join(sorted(planner_context.keys()))
            dataset_summary = (
                "Você deve considerar todos os datasets carregados nesta sessão: "
                f"{dataset_names}. "
                "Use os nomes exatos e as colunas disponíveis para responder, "
                "sem inventar dados."
            )

        prompt = f"{SYSTEM_PROMPT}\n\n{dataset_summary}".strip()
        return [SystemMessage(content=prompt), HumanMessage(content=question)]

    def _ensure_provider_available(
        self,
        provider: str,
        estimated_tokens: int = 0,
        query_id: str | None = None,
    ) -> str | None:
        model = self._model(provider)
        remaining = self.provider_health.remaining(provider, model)
        state = self.provider_health.state(provider, model)
        if state == ProviderHealth.OPEN:
            self._log_decision(
                query_id,
                provider,
                "LOCAL_CIRCUIT_OPEN",
                provider_called=False,
                block_source="circuit_breaker",
            )
            raise self._cooldown_error(provider, remaining, "circuit_breaker")
        if remaining:
            self._log_decision(
                query_id,
                provider,
                "LOCAL_COOLDOWN",
                provider_called=False,
                block_source="cooldown",
            )
            raise self._cooldown_error(provider, remaining, "cooldown")
        budget = self.provider_health.budget(provider, model)
        if budget.get("remaining_requests") is not None and budget["remaining_requests"] <= 0:
            self._log_budget_block(query_id, provider, budget)
            raise ProviderRateLimitError(
                "Limite de requisicoes do provedor atingido.",
                provider=provider,
                metadata={**budget, "provider_rate_limit_source": "local_budget"},
            )
        if budget.get("remaining_tokens") is not None and budget["remaining_tokens"] <= 0:
            self._log_budget_block(query_id, provider, budget)
            raise ProviderRateLimitError(
                "Limite de tokens do provedor atingido.",
                provider=provider,
                metadata={**budget, "provider_rate_limit_source": "local_budget"},
            )
        reservation_id = self.provider_health.reserve(provider, estimated_tokens, model)
        if reservation_id is None:
            self._log_budget_block(query_id, provider, budget)
            raise ProviderRateLimitError(
                "A consulta nao cabe no budget conhecido do provedor.",
                provider=provider,
                metadata={**budget, "provider_rate_limit_source": "local_budget"},
                retry_after_seconds=self._retry_after_seconds(
                    {"x-ratelimit-reset-tokens": str(budget.get("token_reset") or "")}, ""
                ),
            )
        return reservation_id

    @staticmethod
    def _estimate_messages(messages: list[Any]) -> int:
        # Estimativa conservadora sem tokenizer externo; inclui o teto de saida.
        characters = sum(len(str(getattr(message, "content", ""))) for message in messages)
        return max(
            GROQ_MAX_COMPLETION_TOKENS,
            (characters + 3) // 4 + GROQ_MAX_COMPLETION_TOKENS,
        )

    def _cooldown_error(
        self,
        provider: str,
        remaining: int | None = None,
        source: str = "cooldown",
    ) -> ProviderRateLimitError:
        seconds = remaining or self.provider_health.remaining(
            provider, self._model(provider)
        ) or PROVIDER_COOLDOWN_SECONDS
        return ProviderRateLimitError(
            "Limite temporário do provedor atingido.",
            provider=provider,
            retry_after_seconds=seconds,
            metadata={"provider_rate_limit_source": source},
        )

    def _record_provider_failure(self, provider: str, error: ProviderError) -> None:
        seconds = error.retry_after_seconds or PROVIDER_COOLDOWN_SECONDS
        metadata = error.metadata
        self.provider_health.update_budget(
            provider,
            self._model(provider),
            token_limit=self._integer(metadata.get("limit_tokens")),
            remaining_tokens=self._integer(metadata.get("remaining_tokens")),
            token_reset=metadata.get("token_reset"),
            token_reset_seconds=self._parse_duration(metadata.get("token_reset", "")),
            request_limit=self._integer(metadata.get("limit_requests")),
            remaining_requests=self._integer(metadata.get("remaining_requests")),
            request_reset=metadata.get("request_reset"),
            request_reset_seconds=self._parse_duration(metadata.get("request_reset", "")),
        )
        is_rate_limit = isinstance(
            error, (ProviderRateLimitError, ProviderQuotaExhaustedError)
        )
        self.provider_health.cooldown(
            provider,
            seconds,
            self._model(provider),
            open_circuit=not is_rate_limit,
        )

    @staticmethod
    def _provider_error(error: Exception, provider: str) -> ProviderError | None:
        status_code = QueryService._status_code(error)
        message = str(error).lower()
        headers = QueryService._provider_headers(error)
        retry_values = [
            QueryService._retry_after_seconds({"retry-after": headers["retry-after"]}, message)
            if headers.get("retry-after") else None,
            QueryService._retry_after_seconds({"x-ratelimit-reset-tokens": headers["x-ratelimit-reset-tokens"]}, message)
            if headers.get("x-ratelimit-reset-tokens") else None,
        ]
        retry_after = max((value for value in retry_values if value is not None), default=None)
        if retry_after is None:
            retry_after = QueryService._retry_after_seconds({}, message)
        wrapped_gemini_429 = (
            provider == "gemini"
            and re.search(r"\b429\b", message) is not None
            and any(marker in message for marker in ("resource_exhausted", "quota exceeded"))
        )
        metadata = {
            "provider_rate_limit_source": provider if status_code == 429 or wrapped_gemini_429 else None,
            "remaining_tokens": QueryService._header_value(headers, "x-ratelimit-remaining-tokens"),
            "token_reset": QueryService._header_value(headers, "x-ratelimit-reset-tokens"),
            "limit_tokens": QueryService._header_value(headers, "x-ratelimit-limit-tokens"),
            "remaining_requests": QueryService._header_value(headers, "x-ratelimit-remaining-requests"),
            "request_reset": QueryService._header_value(headers, "x-ratelimit-reset-requests"),
            "limit_requests": QueryService._header_value(headers, "x-ratelimit-limit-requests"),
        }
        metadata = {key: value for key, value in metadata.items() if value is not None}
        if isinstance(error, ProviderError):
            return error
        if isinstance(error, TimeoutError):
            return ProviderTimeoutError("O provedor excedeu o tempo limite.", provider=provider)
        if isinstance(error, ProviderNotConfiguredError):
            return error
        if status_code == 429 or wrapped_gemini_429:
            if any(marker in message for marker in ("quota", "resource_exhausted", "insufficient_quota")):
                text = "Cota do provedor de IA esgotada."
                return ProviderQuotaExhaustedError(
                    f"{text} Aguarde cerca de {retry_after}s." if retry_after else text,
                    provider=provider,
                    retry_after_seconds=retry_after,
                    metadata=metadata,
                )
            text = "Limite temporário do provedor atingido."
            return ProviderRateLimitError(
                f"{text} Aguarde cerca de {retry_after}s." if retry_after else text,
                provider=provider,
                retry_after_seconds=retry_after,
                metadata=metadata,
            )
        if isinstance(error, httpx.ReadTimeout):
            return ProviderTimeoutError(
                "O provedor excedeu o tempo limite.",
                provider=provider,
            )

        if status_code in {408, 409, 500, 502, 503, 504} or any(
            marker in message
            for marker in (
                "temporarily unavailable",
                "service unavailable",
                "not configured",
                "authentication",
            )
        ):
            return ProviderUnavailableError(
                "O provedor de IA está temporariamente indisponível.",
                provider=provider,
                retry_after_seconds=retry_after,
                metadata=metadata,
            )

        return None

    @staticmethod
    def _provider_headers(error: Exception) -> dict[str, str]:
        candidates = [
            getattr(error, "headers", None),
            getattr(getattr(error, "response", None), "headers", None),
            getattr(error, "response_metadata", None),
        ]
        for candidate in candidates:
            if candidate:
                if isinstance(candidate, dict) and isinstance(candidate.get("headers"), dict):
                    candidate = candidate["headers"]
                return {str(key).lower(): str(value) for key, value in candidate.items()}
        return {}

    @staticmethod
    def _status_code(error: Exception) -> int | None:
        value = getattr(error, "status_code", None)
        if value is None:
            value = getattr(getattr(error, "response", None), "status_code", None)
        return QueryService._integer(value)

    @staticmethod
    def _header_value(headers: dict[str, str], name: str) -> str | None:
        return headers.get(name.lower())

    @staticmethod
    def _retry_after_seconds(headers: dict[str, str], message: str) -> int | None:
        raw = headers.get("retry-after") or headers.get("x-ratelimit-reset-tokens")
        if raw:
            value = QueryService._parse_duration(raw)
            if value is not None:
                return value
        match = re.search(
            r"(?:try again|retry) in\s+([\d.]+)\s*s", message, re.IGNORECASE
        )
        return max(1, math.ceil(float(match.group(1)))) if match else None

    @staticmethod
    def _parse_duration(raw: str) -> int | None:
        """Aceita 3, 3s, 1m, 1m30s e rejeita lixo sem converter errado."""
        text = str(raw).strip().lower()
        if re.fullmatch(r"\d+(?:\.\d+)?", text):
            return max(1, math.ceil(float(text)))
        matches = re.findall(r"(\d+(?:\.\d+)?)\s*(ms|s|m|h)", text)
        if not matches or "".join(f"{number}{unit}" for number, unit in matches) != re.sub(r"\s+", "", text):
            return None
        seconds = sum(
            float(number) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
            for number, unit in matches
        )
        return max(1, math.ceil(seconds)) if seconds >= 0 else None

    @staticmethod
    def _compact_tool_result(result: Any) -> str:
        if not isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False, default=str)
        compact = dict(result)
        rows = compact.get("result")
        if isinstance(rows, list) and len(rows) > 20:
            compact["result"] = rows[:20]
            compact["omitted_rows"] = len(rows) - 20
        return json.dumps(compact, ensure_ascii=False, default=str)

    @staticmethod
    def _answer_from_result(result: dict[str, Any]) -> str:
        if result.get("operation") == "count":
            count = int(result.get("result", 0))
            distinct_column = result.get("distinct_column")

            if distinct_column:
                return f"A consulta encontrou {count} valores únicos em '{distinct_column}'."

            return f"A consulta encontrou {count} registros."

        rows = result.get("result", [])
        returned = int(result.get("returned_rows", len(rows)))

        if result.get("operation") == "aggregate" and rows:
            summary = QueryService._summarize_rows(rows)
            if summary:
                return summary

        return f"A consulta retornou {returned} resultado(s) na tabela."

    @staticmethod
    def _summarize_rows(rows: list[dict[str, Any]], max_rows: int = 5) -> str | None:
        """Monta uma frase legível a partir de agregações (poucas colunas).
        Nunca atua sobre linhas brutas de 'list' (que têm muitas colunas)."""
        if not rows or any(len(row) > 4 for row in rows):
            return None

        def format_row(row: dict[str, Any]) -> str:
            return ", ".join(
                f"{key}: {QueryService._format_value(value)}" for key, value in row.items()
            )

        if len(rows) == 1:
            return f"Resultado: {format_row(rows[0])}."

        items = "; ".join(format_row(row) for row in rows[:max_rows])
        suffix = "" if len(rows) <= max_rows else f" (mostrando os {max_rows} primeiros)"
        return f"Resultados: {items}{suffix}."

    @staticmethod
    def _format_value(value: Any) -> str:
        if isinstance(value, float):
            return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return str(value)

    @staticmethod
    def _log_model_call(provider: str, response: Any, started_at: float, attempt: int, query_id: str | None = None) -> None:
        usage = QueryService._usage(response)
        logger.info(
            "llm_call query_id=%s llm_call_id=%s provider=%s model=%s iteration=%d tool=%s status=success latency_ms=%d input_tokens=%s output_tokens=%s total_tokens=%s attempt=%d",
            query_id,
            f"{query_id}:call:{attempt}" if query_id else None,
            provider,
            GROQ_MODEL if provider == "groq" else GEMINI_MODEL,
            attempt,
            ",".join(call.get("name", "") for call in (getattr(response, "tool_calls", None) or [])),
            round((time.monotonic() - started_at) * 1000),
            usage.get("input_tokens", usage.get("prompt_tokens", usage.get("promptTokens"))),
            usage.get("output_tokens", usage.get("completion_tokens", usage.get("completionTokens"))),
            usage.get("total_tokens", usage.get("totalTokens")),
            attempt,
        )

    @staticmethod
    def _usage(response: Any) -> dict[str, int]:
        metadata = getattr(response, "usage_metadata", None) or getattr(response, "response_metadata", {}) or {}
        usage = metadata.get("token_usage", metadata) if isinstance(metadata, dict) else {}
        if isinstance(usage, dict) and "tokenUsage" in usage:
            usage = usage["tokenUsage"]
        result = {}
        for target, aliases in {
            "input_tokens": ("input_tokens", "prompt_tokens", "promptTokens"),
            "output_tokens": ("output_tokens", "completion_tokens", "completionTokens"),
            "total_tokens": ("total_tokens", "totalTokens"),
        }.items():
            for alias in aliases:
                value = QueryService._integer(usage.get(alias)) if isinstance(usage, dict) else None
                if value is not None:
                    result[target] = value
                    break
        return result

    def _update_budget(self, provider: str, response: Any) -> None:
        usage = getattr(response, "usage_metadata", None) or {}
        if not isinstance(usage, dict):
            usage = {}
        usage = usage.get("token_usage", usage)
        headers = self._provider_headers(response)
        self.provider_health.update_budget(
            provider,
            self._model(provider),
            token_limit=self._integer(usage.get("input_token_limit") or headers.get("x-ratelimit-limit-tokens")),
            remaining_tokens=self._integer(headers.get("x-ratelimit-remaining-tokens")),
            token_reset=headers.get("x-ratelimit-reset-tokens"),
            token_reset_seconds=self._parse_duration(headers.get("x-ratelimit-reset-tokens", "")),
            request_limit=self._integer(headers.get("x-ratelimit-limit-requests")),
            remaining_requests=self._integer(headers.get("x-ratelimit-remaining-requests")),
            request_reset=headers.get("x-ratelimit-reset-requests"),
            request_reset_seconds=self._parse_duration(headers.get("x-ratelimit-reset-requests", "")),
        )

    @staticmethod
    def _integer(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _log_model_failure(
        provider: str,
        started_at: float,
        attempt: int,
        status: str,
        error: Exception | None,
        query_id: str | None = None,
    ) -> None:
        headers = QueryService._provider_headers(error) if error else {}
        logger.info(
            "llm_call query_id=%s llm_call_id=%s provider=%s model=%s iteration=%d status=%s status_code=%s latency_ms=%d input_tokens=%s output_tokens=%s total_tokens=%s remaining_tokens=%s token_reset=%s retry_after=%s attempt=%d",
            query_id,
            f"{query_id}:call:{attempt}" if query_id else None,
            provider,
            GROQ_MODEL if provider == "groq" else GEMINI_MODEL,
            attempt,
            status,
            QueryService._status_code(error) if error else None,
            round((time.monotonic() - started_at) * 1000),
            None,
            None,
            None,
            QueryService._header_value(headers, "x-ratelimit-remaining-tokens"),
            QueryService._header_value(headers, "x-ratelimit-reset-tokens"),
            QueryService._header_value(headers, "retry-after"),
            attempt,
        )

    @staticmethod
    def _result_as_data(result: dict[str, Any] | None) -> dict[str, Any] | None:
        if not result:
            return None
        operation = result.get("operation")
        value = result.get("result")
        if operation == "count":
            return {"type": "count", "value": int(to_json_safe(value))}
        if isinstance(value, list):
            rows = to_json_safe(value)
            columns = []
            for row in rows:
                for column in row:
                    if column not in columns:
                        columns.append(column)
            return {
                "type": "table",
                "columns": columns,
                "rows": rows,
                "truncated": bool(result.get("truncated", False)),
                "returnedRows": int(result.get("returned_rows", len(rows))),
            }
        return None
