from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for the agent platform."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mock_mode: bool = False
    gemini_text_model: str = "gemini-3.5-flash"


@lru_cache
def get_settings() -> Settings:
    """Returns a cached instance of the Settings object."""
    return Settings()
