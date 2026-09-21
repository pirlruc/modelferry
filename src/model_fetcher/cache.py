"""Local artifact cache with atomic writes and SHA-256 verification."""

import hashlib
import os
from collections.abc import Iterator
from pathlib import Path

from model_fetcher.exceptions import DownloadError
from model_fetcher.models import DownloadResult

_HASH_CHUNK = 1024 * 1024
_SHA256_LENGTH = 64


def normalize_sha256(value: str | None) -> str | None:
    """Normalize an optional SHA-256 digest.

    Args:
        value: Digest, optionally prefixed with ``sha256:``.

    Returns:
        Lowercase hex digest, or ``None`` when ``value`` is missing.

    Raises:
        DownloadError: If the value is not a SHA-256 hex digest.
    """
    if value is None:
        return None

    text = value.strip().lower().removeprefix("sha256:")
    if len(text) != _SHA256_LENGTH or any(char not in "0123456789abcdef" for char in text):
        raise DownloadError(f"Invalid SHA-256 checksum: {value!r}")

    return text


def cache_segment(value: str) -> str:
    """Encode one cache path field so it cannot escape the cache root.

    Slashes are percent-encoded so a project path such as ``group/app`` stays a
    single directory. ``.`` and ``..`` segments are rejected.

    Args:
        value: Raw project, model, version, provider, or file name.

    Returns:
        A single relative path segment.

    Raises:
        DownloadError: If the value is empty, absolute, or contains parent segments.
    """
    if not value or value.strip() != value:
        raise DownloadError(f"Cache path segment is blank or padded: {value!r}")

    if "\x00" in value or "\\" in value or value.startswith("/"):
        raise DownloadError(f"Cache path segment is not allowed: {value!r}")

    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise DownloadError(f"Cache path segment is not allowed: {value!r}")

    return value.replace("/", "%2F")


def file_sha256(path: Path) -> str:
    """Hash a file with SHA-256.

    Args:
        path: File to read.

    Returns:
        Lowercase hexadecimal digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(_HASH_CHUNK)
            if not block:
                break

            digest.update(block)

    return digest.hexdigest()


class CacheManager:
    """Store artifacts under ``<cache>/<provider>/<project>/<model>/<version>/<file>``."""

    def __init__(self, cache_dir: Path) -> None:
        """Create a cache rooted at ``cache_dir``.

        Args:
            cache_dir: Absolute cache root. The directory is created on write.
        """
        self.cache_dir = cache_dir

    def destination(
        self,
        *,
        provider: str,
        project_id: str,
        model_name: str,
        version: str,
        file_name: str,
        target_dir: Path | None = None,
    ) -> Path:
        """Resolve the final path for an artifact.

        Args:
            provider: Provider directory name.
            project_id: Project id or path.
            model_name: Model or package name.
            version: Artifact version.
            file_name: Single file name, without directories.
            target_dir: When set, place the file directly in this directory.

        Returns:
            Destination path for the artifact.

        Raises:
            DownloadError: If any path field is unsafe, or ``file_name`` contains a slash.
        """
        if "/" in file_name:
            raise DownloadError("file_name must be a single path segment")

        safe_file = cache_segment(file_name)
        if target_dir is not None:
            return target_dir / safe_file

        relative = Path(
            cache_segment(provider),
            cache_segment(project_id),
            cache_segment(model_name),
            cache_segment(version),
            safe_file,
        )
        return self.cache_dir / relative

    def lookup(
        self,
        path: Path,
        *,
        expected_sha256: str | None = None,
    ) -> DownloadResult | None:
        """Return a cached download when the file is complete and the digest matches.

        A sibling ``<file>.downloading`` marker means a write is in progress or was
        interrupted, so the destination is ignored. When a ``<file>.sha256`` sidecar
        exists, it must match the bytes on disk.

        Args:
            path: Candidate artifact path.
            expected_sha256: Digest required by the caller or the registry.

        Returns:
            A cached result, or ``None`` when the file should be downloaded again.
        """
        digest = self._validate(path, expected_sha256=expected_sha256)
        if digest is None:
            return None

        return DownloadResult(
            local_path=path,
            is_cached=True,
            size_bytes=path.stat().st_size,
            sha256_hash=digest,
        )

    def write_atomic(
        self,
        destination: Path,
        chunks: Iterator[bytes],
        *,
        expected_sha256: str | None = None,
        expected_size: int | None = None,
    ) -> DownloadResult:
        """Stream bytes to ``<file>.downloading`` and rename only after verification.

        Args:
            destination: Final artifact path.
            chunks: File body in order.
            expected_sha256: Digest the bytes must match.
            expected_size: Content length the bytes must match.

        Returns:
            The verified download result with ``is_cached`` set to false.

        Raises:
            DownloadError: If the stream is empty, the size differs, or the digest differs.
        """
        expected = normalize_sha256(expected_sha256)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".downloading")
        try:
            size, file_hash = _stream_to(temporary, chunks)
            _assert_complete(destination.name, size, file_hash, expected, expected_size)
            os.replace(temporary, destination)
            _write_sidecar(destination, file_hash)
        except Exception:  # pylint: disable=broad-exception-caught
            # The caller-supplied stream can fail in provider-specific ways.
            temporary.unlink(missing_ok=True)
            raise

        return DownloadResult(
            local_path=destination,
            is_cached=False,
            size_bytes=size,
            sha256_hash=file_hash,
        )

    def _validate(self, path: Path, *, expected_sha256: str | None) -> str | None:
        """Return the on-disk digest when the artifact is safe to reuse.

        Args:
            path: Candidate artifact path.
            expected_sha256: Optional digest that must match the file.

        Returns:
            The lowercase digest, or ``None`` when the file must be fetched again.
        """
        if not _cache_file_ready(path):
            return None

        actual = file_sha256(path)
        if not _sidecar_matches(path, actual):
            return None

        expected = normalize_sha256(expected_sha256)
        if expected is not None and actual != expected:
            return None

        return actual


def _stream_to(temporary: Path, chunks: Iterator[bytes]) -> tuple[int, str]:
    """Write chunks to ``temporary`` and return the size and SHA-256.

    Args:
        temporary: Incomplete download path.
        chunks: File body in order.

    Returns:
        Byte count and lowercase digest of the bytes that were written.
    """
    digest = hashlib.sha256()
    size = 0
    with temporary.open("wb") as handle:
        for chunk in chunks:
            if not chunk:
                continue

            handle.write(chunk)
            digest.update(chunk)
            size += len(chunk)

        handle.flush()
        os.fsync(handle.fileno())

    return size, digest.hexdigest()


def _assert_complete(
    name: str,
    size: int,
    file_hash: str,
    expected_sha256: str | None,
    expected_size: int | None,
) -> None:
    """Reject an empty, short, or mismatched download.

    Args:
        name: Artifact file name used in error messages.
        size: Bytes written.
        file_hash: Digest of the bytes written.
        expected_sha256: Required digest, when the caller has one.
        expected_size: Required length, when the caller has one.

    Raises:
        DownloadError: If the stream is empty, short, or the digest differs.
    """
    if size == 0:
        raise DownloadError(f"Downloaded artifact {name} was empty")

    if expected_size is not None and size != expected_size:
        raise DownloadError(
            f"Incomplete download for {name}: received {size} bytes, expected {expected_size}",
        )

    if expected_sha256 is not None and file_hash != expected_sha256:
        raise DownloadError(
            f"SHA-256 mismatch for {name}: expected {expected_sha256}, computed {file_hash}",
        )


def _write_sidecar(destination: Path, file_hash: str) -> None:
    """Replace the checksum sidecar after the artifact itself is in place.

    Args:
        destination: Final artifact path.
        file_hash: Digest to record.
    """
    sidecar = Path(str(destination) + ".sha256")
    sidecar_tmp = Path(str(sidecar) + ".downloading")
    sidecar_tmp.write_text(f"{file_hash}\n", encoding="utf-8")
    os.replace(sidecar_tmp, sidecar)


def _cache_file_ready(path: Path) -> bool:
    """Return whether ``path`` is a finished non-empty file.

    Args:
        path: Candidate artifact path.

    Returns:
        False when a sibling download marker exists or the file is missing or empty.
    """
    partial = path.with_name(path.name + ".downloading")
    return not partial.exists() and path.is_file() and path.stat().st_size > 0


def _sidecar_matches(path: Path, actual: str) -> bool:
    """Return whether a checksum sidecar agrees with ``actual``.

    Args:
        path: Artifact path.
        actual: Digest of the bytes on disk.

    Returns:
        True when no sidecar exists or its first field equals ``actual``.
    """
    sidecar = Path(str(path) + ".sha256")
    if not sidecar.is_file():
        return True

    recorded = sidecar.read_text(encoding="utf-8").strip().split()
    return bool(recorded) and recorded[0].lower() == actual
