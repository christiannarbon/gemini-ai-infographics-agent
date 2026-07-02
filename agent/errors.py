"""Domain exception classes for the Gemini AI Infographics Agent."""


class AgentError(Exception):
    """Base class for all agent domain errors."""


class ConfigError(AgentError):
    """Raised when required configuration/credentials are missing or invalid."""


class ArticleFetchError(AgentError):
    """Raised when the article body cannot be retrieved."""


class ArticleTooLargeError(ArticleFetchError):
    """Raised when the article body exceeds the byte cap."""


class GeminiError(AgentError):
    """Raised when a Gemini API call fails (non-fallback)."""


class ArtifactStorageError(AgentError):
    """Raised when storing an artifact fails."""


class SignedUrlError(ArtifactStorageError):
    """Raised when generating a signed artifact URL fails."""


class RuntimeContractError(AgentError):
    """Raised when an Agent Runtime response is missing/invalid."""
