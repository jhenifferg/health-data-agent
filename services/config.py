from dotenv import load_dotenv
import os

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
_CONFIGURED_AI_PROVIDER = os.getenv("AI_PROVIDER")
AI_PROVIDER = (
    _CONFIGURED_AI_PROVIDER
    or ("gemini" if GOOGLE_API_KEY else "groq" if GROQ_API_KEY else "gemini")
).lower()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        return value if value > 0 else default
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
        return value if value > 0 else default
    except ValueError:
        return default


MAX_UPLOAD_BYTES = _env_int("MAX_UPLOAD_BYTES", 500 * 1024 * 1024)
MAX_ZIP_MEMBERS = _env_int("MAX_ZIP_MEMBERS", 1000)
MAX_ZIP_MEMBER_BYTES = _env_int("MAX_ZIP_MEMBER_BYTES", 500 * 1024 * 1024)
MAX_ZIP_UNCOMPRESSED_BYTES = _env_int(
    "MAX_ZIP_UNCOMPRESSED_BYTES", 1024 * 1024 * 1024
)
MAX_AGENT_ITERATIONS = _env_int("MAX_AGENT_ITERATIONS", 5)
AGENT_REQUEST_TIMEOUT_SECONDS = _env_float("AGENT_REQUEST_TIMEOUT_SECONDS", 60.0)
AGENT_RETRIES = _env_int("AGENT_RETRIES", 2)
GROQ_MAX_RETRIES = _env_int("GROQ_MAX_RETRIES", 0)
GROQ_MAX_CONCURRENT_REQUESTS = _env_int("GROQ_MAX_CONCURRENT_REQUESTS", 1)
GROQ_MAX_COMPLETION_TOKENS = _env_int("GROQ_MAX_COMPLETION_TOKENS", 2048)
MAX_QUERY_RESULT_ROWS = _env_int("MAX_QUERY_RESULT_ROWS", 1000)
PROVIDER_COOLDOWN_SECONDS = _env_int("PROVIDER_COOLDOWN_SECONDS", 20)



def is_ai_configured() -> bool:
    if AI_PROVIDER == "groq":
        return bool(GROQ_API_KEY)
    return bool(GOOGLE_API_KEY)


def ai_configuration_error() -> str | None:
    if AI_PROVIDER not in {"gemini", "groq"}:
        return "AI_PROVIDER deve ser 'gemini' ou 'groq'."
    if AI_PROVIDER == "groq" and not GROQ_API_KEY:
        return "GROQ_API_KEY não foi configurada para o provider Groq."
    if AI_PROVIDER == "gemini" and not GOOGLE_API_KEY:
        return "GOOGLE_API_KEY não foi configurada para o provider Gemini."
    return None


def selected_ai_credentials() -> tuple[str | None, str]:
    if AI_PROVIDER == "groq":
        return GROQ_API_KEY, GROQ_MODEL
    return GOOGLE_API_KEY, GEMINI_MODEL
