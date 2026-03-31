class CMMError(Exception):
    """Base exception for the project."""


class AnalyzerError(CMMError):
    """Raised when script analysis fails."""


class ConfigError(CMMError):
    """Raised when configuration is invalid."""


class ProviderError(CMMError):
    """Raised when an external provider fails."""


class RenderError(CMMError):
    """Raised when card rendering fails."""
