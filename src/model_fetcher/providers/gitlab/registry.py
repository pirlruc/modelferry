"""GitLab Model Registry and Generic Package Registry downloads."""

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from model_fetcher.base import BaseRegistryProvider
from model_fetcher.cache import CacheManager, normalize_sha256
from model_fetcher.config import FetcherConfig
from model_fetcher.exceptions import DownloadError, ModelNotFoundError
from model_fetcher.models import DownloadResult, ModelCoordinates
from model_fetcher.providers.gitlab.http import GitLabHttp, project_path

logger = logging.getLogger(__name__)

_FILE_KEYS = ("file_name", "filename", "name")
_SHA_KEYS = ("file_sha256", "sha256", "file_sha256_checksum")


class GitLabRegistryProvider(BaseRegistryProvider):
    """Download one file from GitLab's model registry or generic package registry.

    Model registry flow:

    1. ``GET /api/v4/projects/:id/ml/models/:model_name/versions/:version``.
    2. If that route is absent, list models and versions and match by name.
    3. ``GET /api/v4/projects/:id/packages/ml_models/:model_version_id/files/:file_name``.

    When the model registry has no such version and ``file_name`` is set, the
    provider falls back to the generic package route
    ``GET /api/v4/projects/:id/packages/generic/:package_name/:version/:file_name``.
    """

    name = "gitlab"

    def __init__(
        self,
        config: FetcherConfig,
        cache: CacheManager,
        client: httpx.Client,
    ) -> None:
        """Create the GitLab registry provider.

        Args:
            config: Resolved GitLab settings.
            cache: Shared artifact cache.
            client: Shared HTTP client.
        """
        super().__init__(config, cache, client)
        self._http = GitLabHttp(config, client)

    def get_version_metadata(self, coordinates: ModelCoordinates) -> dict[str, Any]:
        """Return the GitLab model version document.

        Args:
            coordinates: Project, model name, and version to resolve.

        Returns:
            Version JSON that includes the numeric ``id`` used by the package API.

        Raises:
            ModelNotFoundError: If the model or version does not exist.
            AuthenticationError: If GitLab rejects the token.
            DownloadError: If the response is not a version document.
        """
        if coordinates.version.startswith("candidate:"):
            return {"id": coordinates.version, "version": coordinates.version}

        project = project_path(coordinates.project_id)
        direct_path = (
            f"/api/v4/projects/{project}/ml/models/"
            f"{quote(coordinates.model_name, safe='')}/versions/"
            f"{quote(coordinates.version, safe='')}"
        )
        direct = self._http.get_json(direct_path)
        found = _match_version(direct, coordinates.version)
        if found is not None:
            return found

        models = self._http.get_pages(f"/api/v4/projects/{project}/ml/models")
        model = _find_named(models, coordinates.model_name)
        if model is None or "id" not in model:
            raise ModelNotFoundError(
                f"Model {coordinates.model_name!r} was not found in project "
                f"{coordinates.project_id!r}",
            )

        versions = self._http.get_pages(
            f"/api/v4/projects/{project}/ml/models/{quote(str(model['id']), safe='')}/versions",
        )
        version = _find_version(versions, coordinates.version)
        if version is None or "id" not in version:
            raise ModelNotFoundError(
                f"Version {coordinates.version!r} of model {coordinates.model_name!r} "
                f"was not found in project {coordinates.project_id!r}",
            )

        return version

    def download_artifact(
        self,
        coordinates: ModelCoordinates,
        *,
        target_dir: Path | None = None,
        force_download: bool = False,
    ) -> DownloadResult:
        """Download one model file into the cache or ``target_dir``.

        A known ``file_name`` that is already cached and valid does not touch the
        network unless ``force_download`` is true.

        Args:
            coordinates: Remote model identity.
            target_dir: Optional directory that replaces the cache layout.
            force_download: When true, fetch the bytes again.

        Returns:
            The verified local file.

        Raises:
            ModelNotFoundError: If neither registry contains the artifact.
            AuthenticationError: If GitLab rejects the token.
            DownloadError: If the stream is incomplete or the checksum does not match.
        """
        if coordinates.file_name and not force_download:
            cached = self._lookup(coordinates, coordinates.file_name, None, target_dir)
            if cached is not None:
                logger.info("Using cached artifact %s", cached.local_path)
                return cached

        try:
            metadata = self.get_version_metadata(coordinates)
        except ModelNotFoundError:
            if coordinates.file_name is None:
                raise

            return self._download_generic(coordinates, target_dir=target_dir)

        file_name, expected_sha = self._select_file(coordinates, metadata)
        if not force_download:
            cached = self._lookup(coordinates, file_name, expected_sha, target_dir)
            if cached is not None:
                logger.info("Using cached artifact %s", cached.local_path)
                return cached

        version_id = quote(str(metadata["id"]), safe="")
        project = project_path(coordinates.project_id)
        model_path = (
            f"/api/v4/projects/{project}/packages/ml_models/{version_id}/files/"
            f"{quote(file_name, safe='')}"
        )
        try:
            return self._download_path(
                coordinates,
                model_path,
                file_name,
                expected_sha,
                target_dir=target_dir,
            )
        except ModelNotFoundError:
            if coordinates.file_name is None:
                raise

            return self._download_generic(
                coordinates,
                target_dir=target_dir,
                expected_sha256=expected_sha,
            )

    def _select_file(
        self,
        coordinates: ModelCoordinates,
        metadata: dict[str, Any],
    ) -> tuple[str, str | None]:
        """Choose the artifact file name and any registry checksum.

        Args:
            coordinates: Requested identity, including an optional file name.
            metadata: Model version document.

        Returns:
            File name and optional SHA-256 digest.

        Raises:
            DownloadError: If several files exist and none was requested.
            ModelNotFoundError: If the requested file is not on the version.
        """
        files = _embedded_files(metadata)
        if coordinates.file_name:
            for item in files:
                if item[0] == coordinates.file_name:
                    return item

            return coordinates.file_name, None

        if not files:
            files = self._package_files(coordinates)

        if len(files) == 1:
            return files[0]

        if not files:
            raise DownloadError(
                f"Model {coordinates.model_name!r} version {coordinates.version!r} "
                "has no files. Pass file_name to download a generic package.",
            )

        names = ", ".join(name for name, _sha in files)
        raise DownloadError(
            f"Model {coordinates.model_name!r} version {coordinates.version!r} has multiple "
            f"files ({names}). Pass file_name.",
        )

    def _package_files(self, coordinates: ModelCoordinates) -> list[tuple[str, str | None]]:
        """List package files associated with a model version.

        Args:
            coordinates: Model identity used as the package name and version.

        Returns:
            File names and optional checksums. An empty list means the package API
            did not identify files; the caller may still know ``file_name``.
        """
        project = project_path(coordinates.project_id)
        packages = self._http.get_pages(
            f"/api/v4/projects/{project}/packages",
            params={
                "package_type": "ml_model",
                "package_name": coordinates.model_name,
                "package_version": coordinates.version,
            },
        )
        if not packages:
            return []

        files: list[tuple[str, str | None]] = []
        for package in packages:
            if not isinstance(package, dict) or "id" not in package:
                continue

            listed = self._http.get_pages(
                f"/api/v4/projects/{project}/packages/{quote(str(package['id']), safe='')}"
                "/package_files",
            )
            if not listed:
                continue

            for item in listed:
                parsed = _file_record(item)
                if parsed is not None:
                    files.append(parsed)

        return files

    def _download_generic(
        self,
        coordinates: ModelCoordinates,
        *,
        target_dir: Path | None,
        expected_sha256: str | None = None,
    ) -> DownloadResult:
        """Download from the generic package registry.

        Args:
            coordinates: Package name, version, and file name.
            target_dir: Optional override directory.
            expected_sha256: Digest to verify, when the model registry provided one.

        Returns:
            The verified local file.

        Raises:
            ModelNotFoundError: If ``file_name`` is missing or GitLab returns 404.
        """
        if coordinates.file_name is None:
            raise ModelNotFoundError(
                f"Model {coordinates.model_name!r} version {coordinates.version!r} "
                f"was not found in project {coordinates.project_id!r}",
            )

        project = project_path(coordinates.project_id)
        path = (
            f"/api/v4/projects/{project}/packages/generic/"
            f"{quote(coordinates.model_name, safe='')}/"
            f"{quote(coordinates.version, safe='')}/"
            f"{quote(coordinates.file_name, safe='')}"
        )
        return self._download_path(
            coordinates,
            path,
            coordinates.file_name,
            expected_sha256,
            target_dir=target_dir,
        )

    def _download_path(
        self,
        coordinates: ModelCoordinates,
        path: str,
        file_name: str,
        expected_sha256: str | None,
        *,
        target_dir: Path | None,
    ) -> DownloadResult:
        """Stream one GitLab file into the cache.

        Args:
            coordinates: Model identity used for the cache path.
            path: API path of the file.
            file_name: Local file name.
            expected_sha256: Digest to verify.
            target_dir: Optional override directory.

        Returns:
            The verified local file.

        Raises:
            ModelNotFoundError: If GitLab returns 404.
            DownloadError: If the body is incomplete or the digest does not match.
        """
        destination = self._cache.destination(
            provider=self.name,
            project_id=coordinates.project_id,
            model_name=coordinates.model_name,
            version=coordinates.version,
            file_name=file_name,
            target_dir=target_dir,
        )
        logger.info("Downloading %s to %s", path, destination)
        with self._http.open_download(path) as response:
            if response.status_code == 404:
                raise ModelNotFoundError(f"Artifact {file_name!r} was not found at {path}")

            expected_size = _content_length(response)
            header_sha = response.headers.get("x-checksum-sha256")
            digest = expected_sha256 or header_sha
            return self._cache.write_atomic(
                destination,
                _iter_bytes(response),
                expected_sha256=digest,
                expected_size=expected_size,
            )

    def _lookup(
        self,
        coordinates: ModelCoordinates,
        file_name: str,
        expected_sha256: str | None,
        target_dir: Path | None,
    ) -> DownloadResult | None:
        """Return a cache hit for this artifact.

        Args:
            coordinates: Model identity.
            file_name: Local file name.
            expected_sha256: Digest the cached bytes must match.
            target_dir: Optional override directory.

        Returns:
            The cached result, or ``None``.
        """
        destination = self._cache.destination(
            provider=self.name,
            project_id=coordinates.project_id,
            model_name=coordinates.model_name,
            version=coordinates.version,
            file_name=file_name,
            target_dir=target_dir,
        )
        return self._cache.lookup(destination, expected_sha256=normalize_sha256(expected_sha256))


def _iter_bytes(response: httpx.Response) -> Iterator[bytes]:
    """Yield download chunks.

    Args:
        response: Open streaming response.

    Yields:
        Body chunks.
    """
    yield from response.iter_bytes(chunk_size=1024 * 1024)


def _content_length(response: httpx.Response) -> int | None:
    """Parse a content-length header.

    Args:
        response: Download response.

    Returns:
        The declared size, or ``None`` when the header is absent or invalid.
    """
    raw = response.headers.get("content-length")
    if raw is None or not raw.isdigit():
        return None

    return int(raw)


def _match_version(payload: Any, version: str) -> dict[str, Any] | None:
    """Return a version object from a direct metadata response.

    Args:
        payload: Decoded JSON, or ``None`` on 404.
        version: Requested version string.

    Returns:
        The version document when it has an ``id``.
    """
    if isinstance(payload, dict) and "id" in payload:
        label = payload.get("version")
        if label is None or str(label) == version:
            return payload

    return _find_version(payload if isinstance(payload, list) else None, version)


def _find_named(items: list[Any] | None, name: str) -> dict[str, Any] | None:
    """Find an object whose ``name`` matches.

    Args:
        items: JSON objects, or ``None`` when the list endpoint returned 404.
        name: Expected name.

    Returns:
        The matching object, or ``None``.
    """
    if not items:
        return None

    for item in items:
        if isinstance(item, dict) and item.get("name") == name:
            return item

    return None


def _find_version(items: list[Any] | None, version: str) -> dict[str, Any] | None:
    """Find a version object.

    Args:
        items: Version documents.
        version: Expected version string.

    Returns:
        The matching document when it includes ``id``.
    """
    if not items:
        return None

    for item in items:
        if isinstance(item, dict) and str(item.get("version", "")) == version and "id" in item:
            return item

    return None


def _embedded_files(metadata: dict[str, Any]) -> list[tuple[str, str | None]]:
    """Read file descriptors embedded in a version document.

    Args:
        metadata: Version JSON.

    Returns:
        File name and checksum pairs.
    """
    files: list[tuple[str, str | None]] = []
    for key in ("files", "artifacts", "package_files"):
        raw = metadata.get(key)
        if not isinstance(raw, list):
            continue

        for item in raw:
            parsed = _file_record(item)
            if parsed is not None:
                files.append(parsed)

    return files


def _file_record(item: Any) -> tuple[str, str | None] | None:
    """Parse one package file object.

    Args:
        item: JSON value from a file list.

    Returns:
        File name and optional checksum, or ``None`` when the name is missing.
    """
    if not isinstance(item, dict):
        return None

    file_name = ""
    for key in _FILE_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value:
            file_name = value
            break

    if not file_name:
        return None

    digest: str | None = None
    for key in _SHA_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value:
            digest = value
            break

    return file_name, digest
