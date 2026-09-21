"""Provider contracts for registries and feature-flag evaluation."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx

from model_fetcher.cache import CacheManager
from model_fetcher.config import FetcherConfig
from model_fetcher.models import DownloadResult, FeatureFlagResolution, ModelCoordinates


class BaseRegistryProvider(ABC):
    """Download versioned model artifacts from one remote registry.

    Subclasses are constructed with the same three collaborators so
    ``ModelFetcher`` can register new platforms without changing its methods:

    ``__init__(self, config: FetcherConfig, cache: CacheManager, client: httpx.Client)``.
    """

    name: str

    def __init__(
        self,
        config: FetcherConfig,
        cache: CacheManager,
        client: httpx.Client,
    ) -> None:
        """Store the shared client collaborators.

        Args:
            config: Resolved authentication and host settings.
            cache: Local artifact store.
            client: HTTP client owned by ``ModelFetcher``.
        """
        self._config = config
        self._cache = cache
        self._client = client

    @abstractmethod
    def download_artifact(
        self,
        coordinates: ModelCoordinates,
        *,
        target_dir: Path | None = None,
        force_download: bool = False,
    ) -> DownloadResult:
        """Download one artifact and return the verified local file.

        Args:
            coordinates: Remote model identity.
            target_dir: Optional directory that replaces the shared cache layout.
            force_download: When true, ignore a valid cached file.

        Returns:
            Download metadata including the local path.
        """

    @abstractmethod
    def get_version_metadata(self, coordinates: ModelCoordinates) -> dict[str, Any]:
        """Return the registry's version document for these coordinates.

        Args:
            coordinates: Remote model identity.

        Returns:
            JSON object describing the version. The shape is provider-specific.
        """


class BaseFlagProvider(ABC):
    """Evaluate a feature flag and extract model coordinates from its payload.

    Constructors use the same ``(config, client)`` pair as
    :class:`BaseRegistryProvider`, without a cache.
    """

    name: str

    def __init__(self, config: FetcherConfig, client: httpx.Client) -> None:
        """Store the shared client collaborators.

        Args:
            config: Resolved authentication and host settings.
            client: HTTP client owned by ``ModelFetcher``.
        """
        self._config = config
        self._client = client

    @abstractmethod
    def evaluate_flag(
        self,
        project_id: str,
        flag_name: str,
        context: dict[str, Any] | None = None,
    ) -> FeatureFlagResolution:
        """Evaluate one flag and parse any embedded model coordinates.

        Args:
            project_id: Project that owns the flag.
            flag_name: Flag to evaluate.
            context: Optional evaluation context. Recognized keys are ``user_id``,
                ``environment``, and ``variant``.

        Returns:
            The enablement state and any resolved model coordinates.
        """
