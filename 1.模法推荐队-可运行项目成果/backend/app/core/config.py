"""
Global configuration for the Model Market Assistant.
Reads from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from functools import lru_cache

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - python-dotenv is expected but config must stay import-safe.
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
if load_dotenv is not None:
    load_dotenv(BASE_DIR / ".env", override=False)


class Settings:
    """Application settings loaded from environment variables."""

    # --- App metadata ---
    APP_NAME: str = "model-market-assistant"
    APP_VERSION: str = "0.1.0"
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    AUTH_MODE: str = os.getenv("AUTH_MODE", "demo").lower()
    AUTH_ADAPTER: str = os.getenv("AUTH_ADAPTER", "demo").lower()
    AUTH_JWT_ISSUER: str = os.getenv("AUTH_JWT_ISSUER", "")
    AUTH_JWT_AUDIENCE: str = os.getenv("AUTH_JWT_AUDIENCE", "")
    AUTH_JWT_PUBLIC_KEY: str = os.getenv("AUTH_JWT_PUBLIC_KEY", "").replace("\\n", "\n")
    AUTH_JWKS_URL: str = os.getenv("AUTH_JWKS_URL", "")
    AUTH_JWT_ALGORITHMS: list[str] = [
        value.strip() for value in os.getenv("AUTH_JWT_ALGORITHMS", "RS256").split(",") if value.strip()
    ]

    # --- Paths ---
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = Path(os.getenv("DATA_DIR") or str(BASE_DIR / "data"))
    BACKEND_DIR: Path = BASE_DIR / "backend"
    RUNTIME_DB_PATH: Path = Path(
        os.getenv("RUNTIME_DB_PATH") or str(BASE_DIR / "data" / "runtime" / "runtime.db")
    )

    # --- Mock / Integration ---
    ENABLE_MOCK: bool = os.getenv("ENABLE_MOCK", "true").lower() == "true"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "mock")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_TIMEOUT_SECONDS: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    LLM_CONNECT_TIMEOUT_SECONDS: float = float(os.getenv("LLM_CONNECT_TIMEOUT_SECONDS", "10"))
    LLM_READ_TIMEOUT_SECONDS: float = float(os.getenv("LLM_READ_TIMEOUT_SECONDS", "60"))
    LLM_TOTAL_TIMEOUT_SECONDS: float = float(os.getenv("LLM_TOTAL_TIMEOUT_SECONDS", "90"))
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "2"))
    LLM_CIRCUIT_FAILURE_THRESHOLD: int = int(os.getenv("LLM_CIRCUIT_FAILURE_THRESHOLD", "3"))
    LLM_CIRCUIT_OPEN_SECONDS: float = float(os.getenv("LLM_CIRCUIT_OPEN_SECONDS", "30"))
    LLM_CACHE_ENABLED: bool = os.getenv("LLM_CACHE_ENABLED", "true").lower() == "true"
    LLM_CACHE_TTL_SECONDS: float = float(os.getenv("LLM_CACHE_TTL_SECONDS", "300"))
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    LLM_TRACE_ENABLED: bool = os.getenv("LLM_TRACE_ENABLED", "true").lower() == "true"
    LLM_TRACE_DIR: Path = Path(os.getenv("LLM_TRACE_DIR") or str(DATA_DIR / "llm_traces"))
    MODEL_MARKET_ADAPTER: str = os.getenv("MODEL_MARKET_ADAPTER", "")
    MODEL_MARKET_BASE_URL: str = os.getenv("MODEL_MARKET_BASE_URL", "")
    MODEL_MARKET_API_KEY: str = os.getenv("MODEL_MARKET_API_KEY", "")
    MODEL_MARKET_TIMEOUT_SECONDS: int = int(os.getenv("MODEL_MARKET_TIMEOUT_SECONDS", "30"))

    # --- CORS ---
    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]

    # --- Server ---
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    RELOAD: bool = os.getenv("RELOAD", "false").lower() == "true"
    REQUEST_MAX_BODY_BYTES: int = int(os.getenv("REQUEST_MAX_BODY_BYTES", str(2 * 1024 * 1024)))
    JSON_MAX_DEPTH: int = int(os.getenv("JSON_MAX_DEPTH", "20"))

    # --- Logging ---
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()
