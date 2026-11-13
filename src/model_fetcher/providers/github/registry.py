"""GitHub Releases asset downloads."""

from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from model_fetcher.base import BaseRegistryProvider
from model_fetcher.cache import CacheManager, normalize_sha256
from model_fetcher.config import FetcherConfig
from model_fetcher.exceptions import DownloadError, ModelNotFoundError
from model_fetcher.models import DownloadResult, ModelCoordinates
from model_fetcher.providers.github.http import GitHubHttp


def repository_path(project_id: str) -> str:
    """Return ``owner/repo`` with each segment escaped.

    Args:
        project_id: ``owner/repo``.

    Returns:
        The escaped path used under ``/repos/``.

    Raises:
        DownloadError: If the id is not exactly two safe segments.
    """
    parts = project_id.split("/")
    if len(parts) != 2 or any(part in {"", ".", ".."} for part in parts):
        raise DownloadError("GitHub project_id must be owner/repo")
    return "/".join(quote(part, safe="") for part in parts)


def _asset_digest(asset: dict[str, Any]) -> str | None:
    """Return the sha256 digest GitHub recorded on an asset.

    Args:
        asset: One release asset object.

    Returns:
        The lowercase hex digest, or ``None`` when the asset has none.
    """
    raw = asset.get("digest")
    if not isinstance(raw, str) or not raw.startswith("sha256:"):
        return None
    return normalize_sha256(raw.removeprefix("sha256:"))


def _named_asset(release: dict[str, Any], file_name: str) -> dict[str, Any]:
    """Find one asset by file name.

    Args:
        release: Release JSON.
        file_name: Asset name.

    Returns:
        The matching asset object.

    Raises:
        ModelNotFoundError: If the release has no such asset.
    """
    assets = release.get("assets")
    if isinstance(assets, list):
        for asset in assets:
            if isinstance(asset, dict) and asset.get("name") == file_name:
                return asset
    raise ModelNotFoundError(f"Release asset {file_name!r} was not found")


class GitHubRegistryProvider(BaseRegistryProvider):
    """Download one GitHub Release asset into the shared cache.

    ``project_id`` is ``owner/repo``. ``version`` is the release tag.
    ``file_name`` is the asset name. When ``file_name`` is omitted, the asset
    whose name equals ``model_name`` is used.
    """

    name = "github"

    def __init__(
        self,
        config: FetcherConfig,
        cache: CacheManager,
        client: httpx.Client,
    ) -> None:
        """Create the GitHub registry provider.

        Args:
            config: Resolved GitHub settings.
            cache: Shared artifact cache.
            client: Shared HTTP client.
        """
        super().__init__(config, cache, client)
        self._http = GitHubHttp(config, client)

    def get_version_metadata(self, coordinates: ModelCoordinates) -> dict[str, Any]:
        """Return the GitHub release document for the tag.

        Args:
            coordinates: Repository and tag.

        Returns:
            The release JSON object.
        """
        repo = repository_path(coordinates.project_id)
        tag = quote(coordinates.version, safe="")
        return self._http.get_json(f"/repos/{repo}/releases/tags/{tag}")

    def download_artifact(  # pylint: disable=duplicate-code
        self,
        coordinates: ModelCoordinates,
        *,
        target_dir: Path | None = None,
        force_download: bool = False,
    ) -> DownloadResult:
        """Download one release asset and verify its digest.

        Args:
            coordinates: Repository, tag, and asset name.
            target_dir: Optional directory that replaces the cache layout.
            force_download: When true, ignore a valid cached file.

        Returns:
            The verified local file.

        Raises:
            DownloadError: If the asset has no sha256 digest.
            ModelNotFoundError: If the release or asset does not exist.
        """
        file_name = coordinates.file_name or coordinates.model_name
        release = self.get_version_metadata(coordinates)
        asset = _named_asset(release, file_name)
        digest = _asset_digest(asset)
        if digest is None:
            raise DownloadError(f"Release asset {file_name!r} has no sha256 digest")

        destination = self._cache.destination(
            provider=self.name,
            project_id=coordinates.project_id,
            model_name=coordinates.model_name,
            version=coordinates.version,
            file_name=file_name,
            target_dir=target_dir,
        )
        if not force_download:
            cached = self._cache.lookup(destination, expected_sha256=digest)
            if cached is not None:
                return cached

        url = asset.get("url")
        if not isinstance(url, str):
            raise DownloadError(f"Release asset {file_name!r} has no download URL")
        size = asset.get("size")
        expected_size = size if isinstance(size, int) else None
        return self._cache.write_atomic(
            destination,
            self._http.stream(url),
            expected_sha256=digest,
            expected_size=expected_size,
            max_bytes=self._config.max_bytes,
        )
