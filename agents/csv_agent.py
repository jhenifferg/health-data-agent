import httpx

from langchain_core.tools import StructuredTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from pipeline.data_manager import DataManager
from services.config import (
    AGENT_REQUEST_TIMEOUT_SECONDS,
    AGENT_RETRIES,
    AI_PROVIDER,
    GEMINI_MODEL,
    GOOGLE_API_KEY,
    GROQ_API_KEY,
    GROQ_MAX_RETRIES,
    GROQ_MAX_COMPLETION_TOKENS,
    GROQ_MODEL,
)

# Alias local mantido para fixtures e integracoes que inspecionam a fabrica.
GROQ_AGENT_RETRIES = GROQ_MAX_RETRIES
from services.exceptions import ProviderNotConfiguredError
from tools.data_tools import DataQuery, describe_data, query_data


def build_tools(data_manager: DataManager, provider: str | None = None) -> list[StructuredTool]:
    query_tool = StructuredTool.from_function(
        func=lambda **kwargs: query_data(DataQuery.model_validate(kwargs), data_manager),
        name="query_data",
        description="Executa um plano estruturado nos dados carregados. Use nomes exatos do contexto.",
        args_schema=DataQuery,
    )
    describe_tool = StructuredTool.from_function(
        func=lambda: _compact_description(describe_data(data_manager)),
        name="describe_data",
        description=(
            "Retorna datasets, número de registros, colunas, tipos e descrições. "
            "Use antes de query_data."
        ),
    )
    # Groq recebe o schema no prompt e nao precisa de uma rodada de descoberta.
    return [query_tool] if (provider or AI_PROVIDER).lower() == "groq" else [describe_tool, query_tool]


def _compact_description(description: dict) -> dict:
    """Keep tool context small enough for providers with strict token limits."""
    return {
        dataset: {
            "rows": metadata.get("rows", 0),
            "columns": metadata.get("columns", []),
            "dtypes": metadata.get("dtypes", {}),
            "descriptions": metadata.get("descriptions", {}),
        }
        for dataset, metadata in description.items()
    }


def create_agent(
    data_manager: DataManager | None = None,
    tools: list[StructuredTool] | None = None,
    provider: str | None = None,
):
    """Cria o modelo com ferramentas ligadas ao DataManager da sessão."""
    selected_provider = (provider or AI_PROVIDER).lower()
    api_key, model = _selected_credentials(selected_provider)
    if not api_key:
        raise ProviderNotConfiguredError(
            f"Chave não configurada para o provedor {selected_provider}",
            provider=selected_provider,
        )

    manager = data_manager or DataManager()
    bound_tools = tools or build_tools(manager, provider=selected_provider)
    # Retry orchestration is centralized in QueryService to honor provider cooldowns.
    retries = GROQ_AGENT_RETRIES if selected_provider == "groq" else 0
    if selected_provider == "groq":
        llm = ChatGroq(
            model=model,
            temperature=0,
            max_tokens=GROQ_MAX_COMPLETION_TOKENS,
            api_key=api_key,
            timeout=AGENT_REQUEST_TIMEOUT_SECONDS,
            max_retries=retries,
            reasoning_effort="medium",
            model_kwargs={"include_reasoning": False},
            http_client=(capture := _GroqResponseCapture()).client,
        )
        return _GroqPlanner(
            llm.with_structured_output(
                _strict_data_query_schema(),
                method="json_schema",
                strict=True,
                include_raw=True,
            ),
            capture,
        )
    else:
        llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=0,
            max_tokens=512,
            google_api_key=api_key,
            request_timeout=AGENT_REQUEST_TIMEOUT_SECONDS,
            retries=AGENT_RETRIES,
            thinking_budget=0,
        )
    return llm.bind_tools(bound_tools)


def _strict_data_query_schema() -> dict:
    """Groq strict mode requires every property and forbids extra keys."""
    schema = DataQuery.model_json_schema()
    schema["required"] = list(schema.get("properties", {}))
    schema["additionalProperties"] = False
    return {
        "name": "DataQuery",
        "description": "Plano unico para consulta tabular deterministica.",
        "parameters": schema,
    }


class _GroqResponseCapture:
    def __init__(self):
        self.headers: dict[str, str] = {}
        self.client = httpx.Client(event_hooks={"response": [self._capture]})

    def _capture(self, response: httpx.Response) -> None:
        self.headers = {str(key).lower(): str(value) for key, value in response.headers.items()}


class _GroqPlanner:
    def __init__(self, runnable, capture: _GroqResponseCapture):
        self.runnable = runnable
        self.capture = capture

    def invoke(self, messages):
        try:
            result = self.runnable.invoke(messages)
        except Exception as error:
            if self.capture.headers and not getattr(error, "headers", None):
                error.headers = self.capture.headers
            raise
        raw = result.get("raw") if isinstance(result, dict) else None
        if raw is not None and self.capture.headers:
            metadata = getattr(raw, "response_metadata", None)
            if isinstance(metadata, dict):
                metadata["headers"] = self.capture.headers
        return result


def _selected_credentials(provider: str = AI_PROVIDER) -> tuple[str | None, str]:
    if provider == "groq":
        return GROQ_API_KEY, GROQ_MODEL
    return GOOGLE_API_KEY, GEMINI_MODEL
