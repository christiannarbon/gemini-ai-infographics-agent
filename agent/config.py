from functools import lru_cache
from typing import Any, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_truthy_bool(v: Any) -> bool:
    """Helper to parse boolean strings like '1', 'true', 'yes', 'on' case-insensitively."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in {"1", "true", "yes", "on"}
    return bool(v)


class Settings(BaseSettings):
    """Configuration settings for the agent platform."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    # --- mock / backend selection ---
    mock_mode: bool = Field(default=True, alias="MOCK_MODE")
    mock_step_delay: float = Field(default=0.45, alias="MOCK_STEP_DELAY")
    agent_backend: str = Field(default="local", alias="AGENT_BACKEND")

    # --- gemini models + retry (attempts, base delay) ---
    gemini_text_model: str = Field(
        default="gemini-3.5-flash", alias="GEMINI_TEXT_MODEL"
    )
    gemini_image_model: str = Field(
        default="gemini-3-pro-image", alias="GEMINI_IMAGE_MODEL"
    )
    gemini_max_attempts: int = Field(default=3, alias="GEMINI_MAX_ATTEMPTS")
    gemini_retry_base_delay_seconds: float = Field(
        default=0.6, alias="GEMINI_RETRY_BASE_DELAY_SECONDS"
    )
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")
    google_genai_use_vertexai: bool = Field(
        default=False, alias="GOOGLE_GENAI_USE_VERTEXAI"
    )

    # --- article fetch byte cap ---
    article_fetch_max_bytes: int = Field(
        default=2_000_000, alias="ARTICLE_FETCH_MAX_BYTES"
    )

    # --- GCS_* (bucket, prefix, signing service account) and artifacts ---
    artifact_dir: str = Field(default="artifacts", alias="ARTIFACT_DIR")
    gcs_bucket: Optional[str] = Field(default=None, alias="GCS_BUCKET")
    gcs_artifact_prefix: str = Field(default="artifacts", alias="GCS_ARTIFACT_PREFIX")
    gcs_signed_url_ttl_seconds: int = Field(
        default=28800, alias="GCS_SIGNED_URL_TTL_SECONDS"
    )
    gcs_signing_service_account: Optional[str] = Field(
        default=None, alias="GCS_SIGNING_SERVICE_ACCOUNT"
    )

    # --- AUTH / APP_* (password, secret key, cookie TTL) ---
    app_password: str = Field(default="", alias="APP_PASSWORD")
    app_secret_key: str = Field(default="", alias="APP_SECRET_KEY")
    k_service: Optional[str] = Field(default=None, alias="K_SERVICE")
    app_env: str = Field(default="", alias="APP_ENV")
    auth_cookie_max_age_seconds: int = Field(
        default=28800, alias="AUTH_COOKIE_MAX_AGE_SECONDS"
    )

    # --- logging (log level, log format) ---
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    app_log_format: str = Field(default="json", alias="APP_LOG_FORMAT")

    # --- AGENT_RUNTIME_* and project id ---
    agent_runtime_location: str = Field(
        default="us-central1", alias="AGENT_RUNTIME_LOCATION"
    )
    agent_display_name: str = Field(
        default="infographics-agent", alias="AGENT_DISPLAY_NAME"
    )
    agent_runtime_staging_bucket: Optional[str] = Field(
        default=None, alias="AGENT_RUNTIME_STAGING_BUCKET"
    )
    agent_runtime_requirements_file: str = Field(
        default="constraints.txt", alias="AGENT_RUNTIME_REQUIREMENTS_FILE"
    )
    google_cloud_location: Optional[str] = Field(
        default=None, alias="GOOGLE_CLOUD_LOCATION"
    )
    agent_runtime_user_id: str = Field(
        default="poc-user", alias="AGENT_RUNTIME_USER_ID"
    )
    agent_runtime_resource_name: Optional[str] = Field(
        default=None, alias="AGENT_RUNTIME_RESOURCE_NAME"
    )
    google_cloud_project: Optional[str] = Field(
        default=None, alias="GOOGLE_CLOUD_PROJECT"
    )
    project_id: Optional[str] = Field(default=None, alias="PROJECT_ID")

    # --- Validators ---

    @field_validator("mock_mode", "google_genai_use_vertexai", mode="before")
    @classmethod
    def validate_bool(cls, v: Any) -> bool:
        return parse_truthy_bool(v)

    @field_validator("article_fetch_max_bytes", mode="before")
    @classmethod
    def validate_article_fetch_max_bytes(cls, v: Any) -> int:
        if v is None:
            return 2_000_000
        try:
            val = int(v)
            return max(1024, val)
        except (ValueError, TypeError):
            return 2_000_000

    @field_validator("gemini_max_attempts", mode="before")
    @classmethod
    def validate_gemini_max_attempts(cls, v: Any) -> int:
        if v is None:
            return 3
        try:
            return max(1, int(v))
        except (ValueError, TypeError):
            return 3

    @field_validator("gemini_retry_base_delay_seconds", mode="before")
    @classmethod
    def validate_gemini_retry_base_delay(cls, v: Any) -> float:
        if v is None:
            return 0.6
        try:
            return max(0.1, float(v))
        except (ValueError, TypeError):
            return 0.6

    @field_validator("gcs_signed_url_ttl_seconds", mode="before")
    @classmethod
    def validate_gcs_signed_url_ttl(cls, v: Any) -> int:
        if v is None:
            return 28800
        try:
            return max(60, int(v))
        except (ValueError, TypeError):
            return 28800

    @field_validator("auth_cookie_max_age_seconds", mode="before")
    @classmethod
    def validate_auth_cookie_max_age(cls, v: Any) -> int:
        if v is None:
            return 28800
        try:
            return max(60, int(v))
        except (ValueError, TypeError):
            return 28800

    # --- Computed Properties ---

    @property
    def use_vertex_ai(self) -> bool:
        """Returns True if the application should use Vertex AI instead of Google AI Studio."""
        return self.google_genai_use_vertexai

    @property
    def has_gemini_credentials(self) -> bool:
        """Returns True if the application has configured Gemini credentials."""
        if self.gemini_api_key or self.google_api_key:
            return True
        return self.use_vertex_ai


@lru_cache
def get_settings() -> Settings:
    """Returns a cached instance of the Settings object."""
    return Settings()
