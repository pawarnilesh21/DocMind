from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    APP_NAME: str = "DocMind"
    APP_VERSION: str = "2.0.0"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    DEBUG: bool = False
    DATABASE_URL: str = ""
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    LLM_MODEL: str = "qwen/qwen3.8-27b"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:8080"]
    ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1", "testserver"]
    COOKIE_SECURE: bool = False
    SESSION_HOURS: int = Field(default=12, ge=1, le=168)
    JWT_SECRET_KEY: SecretStr = SecretStr("")
    JWT_ISSUER: str = "docmind"
    JWT_AUDIENCE: str = "docmind-web"
    MAX_FILE_BYTES: int = Field(default=20 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    MAX_DOCUMENTS_PER_USER: int = Field(default=100, ge=1, le=10000)
    MAX_PAGES: int = Field(default=300, ge=1, le=1000)
    MAX_EXTRACTED_CHARS: int = Field(default=500_000, ge=1000, le=2_000_000)
    MAX_CHUNKS: int = Field(default=750, ge=1, le=2500)
    CHUNK_SIZE: int = Field(default=1200, ge=200, le=4000)
    CHUNK_OVERLAP: int = Field(default=200, ge=0)
    SIMILARITY_THRESHOLD: float = Field(default=0.35, ge=-1, le=1)
    PROVIDER_TIMEOUT_SECONDS: int = Field(default=30, ge=1, le=90)
    JOB_TIMEOUT_SECONDS: int = Field(default=600, ge=30, le=1800)
    JOB_MAX_ATTEMPTS: int = Field(default=3, ge=1, le=5)
    WORKER_POLL_SECONDS: float = Field(default=2, ge=0.1, le=30)
    LOGIN_REQUESTS_PER_MINUTE: int = Field(default=10, ge=1)
    CHAT_REQUESTS_PER_MINUTE: int = Field(default=10, ge=1)
    CHAT_REQUESTS_PER_DAY: int = Field(default=200, ge=1)
    UPLOAD_REQUESTS_PER_HOUR: int = Field(default=20, ge=1)

    @model_validator(mode="after")
    def validate_configuration(self):
        key = self.JWT_SECRET_KEY.get_secret_value()
        if len(key.encode()) < 32 or key.startswith("replace_with_"):
            raise ValueError("JWT_SECRET_KEY must be a random secret of at least 32 bytes")
        if self.CHUNK_OVERLAP >= self.CHUNK_SIZE:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        if self.ENVIRONMENT == "production":
            if not self.COOKIE_SECURE or self.DEBUG:
                raise ValueError("Production requires COOKIE_SECURE=true and DEBUG=false")
            if not self.DATABASE_URL.startswith(("postgresql://", "postgres://")):
                raise ValueError("Production requires PostgreSQL")
            if not self.GEMINI_API_KEY or not self.GROQ_API_KEY:
                raise ValueError("Both provider API keys are required")
            if not self.ALLOWED_ORIGINS or any(not x.startswith("https://") for x in self.ALLOWED_ORIGINS):
                raise ValueError("Production requires explicit HTTPS origins")
            if not self.ALLOWED_HOSTS or "*" in self.ALLOWED_HOSTS:
                raise ValueError("Production requires explicit allowed hosts")
        return self


settings = Settings()
