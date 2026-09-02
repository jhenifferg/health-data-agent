class DatasetNotFoundError(Exception):
    code = "dataset_not_found"


class UnsupportedFileError(Exception):
    code = "unsupported_file_type"


class InvalidDatasetError(Exception):
    code = "dataset_load_failed"


class UploadTooLargeError(InvalidDatasetError):
    code = "upload_too_large"


class UnsafeZipEntryError(InvalidDatasetError):
    code = "unsafe_zip_entry"


class InvalidZipError(InvalidDatasetError):
    code = "invalid_zip"


class NoCsvFilesFoundError(InvalidDatasetError):
    code = "no_csv_files_found"


class ZipLimitExceededError(InvalidDatasetError):
    code = "zip_limit_exceeded"


class AIUnavailableError(Exception):
    code = "ai_provider_unavailable"


class AgentExecutionError(Exception):
    code = "query_execution_error"


class UnknownToolError(AgentExecutionError):
    code = "unknown_tool"


class ToolExecutionError(AgentExecutionError):
    code = "tool_execution_failed"


class AgentTimeoutError(AgentExecutionError):
    code = "agent_timeout"


class ProviderError(AgentExecutionError):
    retryable = True

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        retry_after_seconds: int | None = None,
        metadata: dict | None = None,
    ):
        super().__init__(message)
        self.provider = provider
        self.retry_after_seconds = retry_after_seconds
        self.metadata = metadata or {}

    def details(self) -> dict:
        return {
            "provider": self.provider,
            "retryable": self.retryable,
            "retry_after_seconds": self.retry_after_seconds,
            **self.metadata,
        }


class ProviderRateLimitError(ProviderError):
    code = "provider_rate_limit"


class ProviderNotConfiguredError(ProviderError, RuntimeError):
    code = "provider_not_configured"
    retryable = False


class ProviderTimeoutError(ProviderError):
    code = "provider_timeout"


class ProviderAuthError(ProviderError):
    code = "provider_auth_error"
    retryable = False


class ProviderQuotaExhaustedError(ProviderError):
    code = "provider_quota_exhausted"


class ProviderUnavailableError(ProviderError):
    code = "provider_unavailable"


class QueryInvalidError(ToolExecutionError):
    code = "query_invalid"


class AgentIterationLimitError(AgentExecutionError):
    code = "agent_iteration_limit"
