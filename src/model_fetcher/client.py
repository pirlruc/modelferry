"""Public facade that downloads artifacts and evaluates feature flags."""

from pathlib import Path
from typing import Any, Self

import httpx
from pydantic import ValidationError

from model_fetcher.base import BaseFlagProvider, BaseRegistryProvider
from model_fetcher.cache import CacheManager
from model_fetcher.config import FetcherConfig
from model_fetcher.exceptions import (
    FeatureFlagError,
    ModelFetcherError,
    ProviderNotSupportedError,
)
from model_fetcher.models import FeatureFlagResolution, ModelCoordinates
from model_fetcher.providers.gitlab import GitLabFlagProvider, GitLabRegistryProvider

ProviderPair = tuple[type[BaseRegistryProvider], type[BaseFlagProvider]]

_PROVIDERS: dict[str, ProviderPair] = {
    "gitlab": (GitLabRegistryProvider, GitLabFlagProvider),
}


def register_provider(
    name: str,
    registry_cls: type[BaseRegistryProvider],
    flag_cls: type[BaseFlagProvider],
) -> None:
    """Register a platform without changing :class:`ModelFetcher`.

    Future providers such as GitHub Releases implement
    :class:`~model_fetcher.base.BaseRegistryProvider` and
    :class:`~model_fetcher.base.BaseFlagProvider`, then call this function.
    Both classes are constructed as ``cls(config, client)`` for flags and
    ``cls(config, cache, client)`` for registries.

    Args:
        name: Value accepted by ``ModelFetcher(provider=...)``.
        registry_cls: Registry implementation.
        flag_cls: Feature-flag implementation.

    Raises:
        ModelFetcherError: If ``name`` is blank.
    """
    cleaned = name.strip()
    if not cleaned:
        raise ModelFetcherError("Provider name must not be empty")

    _PROVIDERS[cleaned] = (registry_cls, flag_cls)


class ModelFetcher:
    """Download a model file, or resolve which file a feature flag points at.

    The class does not deserialize, load, or execute models. Both download methods
    return the local ``Path`` of a verified artifact.

    Use the client as a context manager so the underlying HTTP connection closes.

    Example:
        >>> with ModelFetcher(token="***") as fetcher:  # doctest: +SKIP
        ...     path = fetcher.download_model(42, "fraud_detector", "v1.4.0")
    """

    def __init__(
        self,
        provider: str = "gitlab",
        base_url: str | None = None,
        token: str | None = None,
        cache_dir: str | Path | None = None,
        timeout: float = 30.0,
        *,
        unleash_instance_id: str | None = None,
        unleash_app_name: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        """Open a fetcher for one registered provider.

        Args:
            provider: Provider name. ``gitlab`` is built in.
            base_url: Registry origin. Falls back to ``GITLAB_URL``.
            token: Access token. Falls back to ``GITLAB_TOKEN`` then ``CI_JOB_TOKEN``.
            cache_dir: Cache root. Defaults to ``~/.cache/model_fetcher``.
            timeout: HTTP timeout in seconds.
            unleash_instance_id: GitLab Unleash instance id for feature flags.
            unleash_app_name: Unleash app name, usually the environment.
            client: Optional HTTP client. When omitted, the fetcher owns a client
                and closes it.

        Raises:
            ProviderNotSupportedError: If ``provider`` was not registered.
            ModelFetcherError: If configuration values are invalid.
        """
        try:
            self.config = FetcherConfig.from_environment(
                provider=provider,
                base_url=base_url,
                token=token,
                cache_dir=cache_dir,
                timeout=timeout,
                unleash_instance_id=unleash_instance_id,
                unleash_app_name=unleash_app_name,
            )
        except ValidationError as exc:
            raise ModelFetcherError(f"Invalid model-fetcher configuration: {exc}") from exc

        pair = _PROVIDERS.get(self.config.provider)
        if pair is None:
            known = ", ".join(sorted(_PROVIDERS))
            raise ProviderNotSupportedError(
                f"Provider {provider!r} is not registered. Known providers: {known}",
            )

        registry_cls, flag_cls = pair
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
        )
        self.cache = CacheManager(self.config.cache_dir)
        self.registry = registry_cls(self.config, self.cache, self._client)
        self.flags = flag_cls(self.config, self._client)

    def close(self) -> None:
        """Close the HTTP client when this fetcher created it."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        """Return this fetcher for use in a ``with`` block.

        Returns:
            This instance.
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        """Close the owned HTTP client.

        Args:
            exc_type: Exception type, if the block failed.
            exc: Exception instance, if the block failed.
            traceback: Traceback, if the block failed.
        """
        self.close()

    def download_model(
        self,
        project_id: str | int,
        model_name: str,
        version: str,
        file_name: str | None = None,
        target_dir: Path | None = None,
        force_download: bool = False,
    ) -> Path:
        """Download one model artifact and return its local path.

        Args:
            project_id: Registry project id or path.
            model_name: Model or generic package name.
            version: Model or package version.
            file_name: Artifact file name. Required when the version has several files
                or when the file lives only in the generic package registry.
            target_dir: Directory that receives the file instead of the shared cache.
            force_download: When true, download again even if a valid file is cached.

        Returns:
            Path of the verified local file.

        Raises:
            ModelNotFoundError: If the model, version, or file does not exist.
            AuthenticationError: If credentials are missing or rejected.
            DownloadError: If the stream or checksum check fails.
            ModelFetcherError: If the coordinates are blank.
        """
        coordinates = _coordinates(project_id, model_name, version, file_name)
        result = self.registry.download_artifact(
            coordinates,
            target_dir=target_dir,
            force_download=force_download,
        )
        return result.local_path

    def get_feature_flag(
        self,
        project_id: str | int,
        flag_name: str,
        context: dict[str, Any] | None = None,
    ) -> FeatureFlagResolution:
        """Evaluate a feature flag and return any model coordinates it carries.

        Args:
            project_id: Project that owns the flag.
            flag_name: Flag name.
            context: Optional ``user_id``, ``environment``, and ``variant``.

        Returns:
            Enablement and the resolved model, when the payload contains one.

        Raises:
            FeatureFlagError: If the flag does not exist.
            AuthenticationError: If credentials are missing or rejected.
        """
        return self.flags.evaluate_flag(str(project_id), flag_name, context)

    def download_from_feature_flag(
        self,
        project_id: str | int,
        flag_name: str,
        context: dict[str, Any] | None = None,
        target_dir: Path | None = None,
        force_download: bool = False,
    ) -> Path:
        """Resolve a flag payload and download the model it names.

        Args:
            project_id: Project that owns the flag. The payload may name another
                project, and that project is used for the download.
            flag_name: Flag whose variant or strategy payload names the model.
            context: Optional ``user_id``, ``environment``, and ``variant``.
            target_dir: Directory that receives the file instead of the shared cache.
            force_download: When true, download again even if a valid file is cached.

        Returns:
            Path of the verified local file.

        Raises:
            FeatureFlagError: If the flag is missing, disabled, or has no model payload.
            ModelNotFoundError: If the resolved artifact does not exist.
            AuthenticationError: If credentials are missing or rejected.
            DownloadError: If the stream or checksum check fails.
        """
        resolution = self.get_feature_flag(project_id, flag_name, context)
        if not resolution.is_enabled or resolution.resolved_model is None:
            raise FeatureFlagError(
                f"Feature flag {flag_name!r} did not resolve a model "
                f"(enabled={resolution.is_enabled})",
            )

        model = resolution.resolved_model
        return self.download_model(
            project_id=model.project_id,
            model_name=model.model_name,
            version=model.version,
            file_name=model.file_name,
            target_dir=target_dir,
            force_download=force_download,
        )


def _coordinates(
    project_id: str | int,
    model_name: str,
    version: str,
    file_name: str | None,
) -> ModelCoordinates:
    """Validate public download arguments.

    Args:
        project_id: Registry project id or path.
        model_name: Model or package name.
        version: Version string.
        file_name: Optional artifact file name.

    Returns:
        Coordinates accepted by registry providers.

    Raises:
        ModelFetcherError: If a required field is blank.
    """
    try:
        return ModelCoordinates(
            project_id=str(project_id),
            model_name=model_name,
            version=version,
            file_name=file_name,
        )
    except ValidationError as exc:
        raise ModelFetcherError(f"Invalid model coordinates: {exc}") from exc
