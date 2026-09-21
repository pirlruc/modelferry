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

try:
    __version__ = version("model-fetcher")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.1.0"

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
