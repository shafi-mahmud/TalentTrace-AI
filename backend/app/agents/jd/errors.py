class JobDescriptionGenerationError(RuntimeError):
    """Base class for controlled job-description generation failures."""


class MissingGenerationConfigurationError(JobDescriptionGenerationError):
    """Raised when generation is invoked without required server configuration."""


class GenerationTimeoutError(JobDescriptionGenerationError):
    """Raised when the configured generation provider times out."""


class GenerationProviderError(JobDescriptionGenerationError):
    """Raised when provider output cannot produce a safe structured draft."""
