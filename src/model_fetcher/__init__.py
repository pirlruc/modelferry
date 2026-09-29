"""Download model artifacts and resolve versions through feature flags.

This package has two responsibilities: stream a model file from a registry into
a local cache, and read a feature flag to learn which model version to fetch.
It returns ``pathlib.Path`` values and does not load or execute models.
"""

from importlib.metadata import PackageNotFoundError, version

from model_fetcher.base import BaseFlagProvider, BaseRegistryProvider
from model_fetcher.cache import CacheManager
from model_fetcher.client import ModelFetcher, register_provider
from model_fetcher.config import FetcherConfig
from model_fetcher.exceptions import (
    AuthenticationError,
    DownloadError,
    FeatureFlagError,
    ModelFetcherError,
    ModelNotFoundError,
    ProviderNotSupportedError,
)
from model_fetcher.models import DownloadResult, FeatureFlagResolution, ModelCoordinates


def _distribution_version() -> str:
    """Return the installed version, or the repo fallback when metadata is absent.

    Returns:
        The distribution version, or ``0.1.0`` when the package is not installed.
    """
    try:
        return version("model-fetcher")
    except PackageNotFoundError:
        return "0.1.0"


__version__ = _distribution_version()

__all__ = [
    "AuthenticationError",
    "BaseFlagProvider",
    "BaseRegistryProvider",
    "CacheManager",
    "DownloadError",
    "DownloadResult",
    "FeatureFlagError",
    "FeatureFlagResolution",
    "FetcherConfig",
    "ModelCoordinates",
    "ModelFetcher",
    "ModelFetcherError",
    "ModelNotFoundError",
    "ProviderNotSupportedError",
    "register_provider",
]
