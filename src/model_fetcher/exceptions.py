"""Error types raised by model-fetcher."""


class ModelFetcherError(Exception):
    """Base error for model download and feature-flag failures."""


class AuthenticationError(ModelFetcherError):
    """Missing or rejected credentials, including HTTP 401 and 403 responses."""


class ModelNotFoundError(ModelFetcherError):
    """The requested model, version, or artifact file does not exist."""


class FeatureFlagError(ModelFetcherError):
    """The feature flag is missing, disabled, or has no model payload."""


class DownloadError(ModelFetcherError):
    """The artifact stream failed, was incomplete, or failed checksum verification."""


class ProviderNotSupportedError(ModelFetcherError):
    """No registry or feature-flag provider is registered under the requested name."""
