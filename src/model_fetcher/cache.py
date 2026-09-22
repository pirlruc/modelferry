"""Local artifact cache with atomic writes and SHA-256 verification."""

from __future__ import annotations

import fcntl
import hashlib
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO

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
        interrupted, so the destination is ignored. A sidecar that equals the expected
        digest and is newer than the file is trusted without reading the file again.
        Otherwise a sidecar must match the bytes on disk. The check holds a shared
        lock so it does not observe a publish between the rename and the sidecar.

        Args:
            path: Candidate artifact path.
            expected_sha256: Digest required by the caller or the registry.

        Returns:
            A cached result, or ``None`` when the file should be downloaded again.
        """
        if not path.is_file():
            return None

        with _file_lock(path.with_name(path.name + ".lock"), fcntl.LOCK_SH):
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
        max_bytes: int | None = None,
    ) -> DownloadResult:
        """Stream bytes to a private temporary file and rename only after verification.

        Each writer uses its own temporary name. ``<file>.lock`` is held only while
        the verified file and its sidecar replace the previous pair, so a reader can
        keep using the previous artifact during the download.

        Args:
            destination: Final artifact path.
            chunks: File body in order.
            expected_sha256: Digest the bytes must match.
            expected_size: Content length the bytes must match.
            max_bytes: Maximum accepted size. ``None`` does not cap the stream.

        Returns:
            The verified download result with ``is_cached`` set to false.

        Raises:
            DownloadError: If the stream is empty, too large, the size differs, or the
                digest differs.
        """
        expected = normalize_sha256(expected_sha256)
        _reject_declared_size(destination.name, expected_size, max_bytes)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(_partial_name(destination.name))
        try:
            size, file_hash = _stream_to(temporary, chunks, max_bytes=max_bytes)
            _assert_complete(destination.name, size, file_hash, expected, expected_size)
            _publish(destination, temporary, file_hash)
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

        expected = normalize_sha256(expected_sha256)
        recorded = _sidecar_digest(path)
        if _sidecar_can_be_trusted(path, recorded, expected):
            return recorded

        actual = file_sha256(path)
        if not _digest_ok(actual, recorded, expected):
            return None

        return actual


def _stream_to(
    temporary: Path,
    chunks: Iterator[bytes],
    *,
    max_bytes: int | None,
) -> tuple[int, str]:
    """Write chunks to ``temporary`` and return the size and SHA-256.

    Args:
        temporary: Incomplete download path.
        chunks: File body in order.
        max_bytes: Maximum accepted size, when the caller set one.

    Returns:
        Byte count and lowercase digest of the bytes that were written.

    Raises:
        DownloadError: If the stream grows past ``max_bytes``.
    """
    digest = hashlib.sha256()
    size = 0
    with temporary.open("wb") as handle:
        for chunk in chunks:
            size = _accept_chunk(handle, digest, size, chunk, max_bytes)

        handle.flush()
        os.fsync(handle.fileno())

    return size, digest.hexdigest()


def _accept_chunk(
    handle: BinaryIO,
    digest: Any,
    size: int,
    chunk: bytes,
    max_bytes: int | None,
) -> int:
    """Write one chunk when it fits under ``max_bytes``.

    Args:
        handle: Binary file opened for writing.
        digest: Running SHA-256.
        size: Bytes already accepted.
        chunk: Next body chunk. Empty chunks are ignored.
        max_bytes: Maximum accepted size, when set.

    Returns:
        The updated byte count.

    Raises:
        DownloadError: If accepting ``chunk`` would pass ``max_bytes``.
    """
    if not chunk:
        return size

    updated = size + len(chunk)
    if max_bytes is not None and updated > max_bytes:
        raise DownloadError(f"Download exceeds max_bytes ({max_bytes})")

    handle.write(chunk)
    digest.update(chunk)
    return updated


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


def _publish(destination: Path, temporary: Path, file_hash: str) -> None:
    """Install a verified file and its sidecar as one locked pair.

    Args:
        destination: Final artifact path.
        temporary: Verified temporary file to move into place.
        file_hash: Digest to record beside the artifact.
    """
    with _file_lock(destination.with_name(destination.name + ".lock"), fcntl.LOCK_EX):
        os.replace(temporary, destination)
        _write_sidecar(destination, file_hash)


def _write_sidecar(destination: Path, file_hash: str) -> None:
    """Replace the checksum sidecar after the artifact itself is in place.

    Args:
        destination: Final artifact path.
        file_hash: Digest to record.
    """
    sidecar = Path(str(destination) + ".sha256")
    sidecar_tmp = Path(str(sidecar) + "." + _partial_name("part"))
    sidecar_tmp.write_text(f"{file_hash}\n", encoding="utf-8")
    os.replace(sidecar_tmp, sidecar)
    _bump_sidecar_mtime(destination, sidecar)


def _bump_sidecar_mtime(destination: Path, sidecar: Path) -> None:
    """Make the sidecar strictly newer than the artifact.

    A crash between the rename and this write leaves the previous sidecar older
    than the new file, so lookup will hash instead of trusting it.

    Args:
        destination: Published artifact.
        sidecar: Checksum file just written for ``destination``.
    """
    file_ns = destination.stat().st_mtime_ns
    if sidecar.stat().st_mtime_ns > file_ns:
        return

    os.utime(sidecar, ns=(file_ns + 1, file_ns + 1))


def _partial_name(name: str) -> str:
    """Return a temporary name that no other writer will open.

    Args:
        name: Final file name.

    Returns:
        ``<name>.downloading.<pid>.<uuid>``.
    """
    return f"{name}.downloading.{os.getpid()}.{uuid.uuid4().hex}"


def _reject_declared_size(name: str, expected_size: int | None, max_bytes: int | None) -> None:
    """Reject a content length that is already over the cap.

    Args:
        name: Artifact file name used in the error.
        expected_size: Declared length, when the caller has one.
        max_bytes: Maximum accepted size, when set.

    Raises:
        DownloadError: If ``expected_size`` is greater than ``max_bytes``.
    """
    if max_bytes is None or expected_size is None or expected_size <= max_bytes:
        return

    raise DownloadError(
        f"Artifact {name} is {expected_size} bytes, above max_bytes ({max_bytes})",
    )


@contextmanager
def _file_lock(path: Path, mode: int) -> Iterator[None]:
    """Hold an advisory lock until the block exits.

    Args:
        path: Lock file created beside the artifact.
        mode: ``fcntl.LOCK_SH`` for readers or ``fcntl.LOCK_EX`` for publishers.

    Yields:
        Nothing. The lock is released when the block exits.
    """
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), mode)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _cache_file_ready(path: Path) -> bool:
    """Return whether ``path`` is a finished non-empty file.

    Args:
        path: Candidate artifact path.

    Returns:
        False when a sibling download marker exists or the file is missing or empty.
    """
    partial = path.with_name(path.name + ".downloading")
    return not partial.exists() and path.is_file() and path.stat().st_size > 0


def _sidecar_digest(path: Path) -> str | None:
    """Return the digest recorded beside ``path``.

    Args:
        path: Artifact path.

    Returns:
        The lowercase digest, or ``None`` when no sidecar exists.
    """
    sidecar = Path(str(path) + ".sha256")
    if not sidecar.is_file():
        return None

    recorded = sidecar.read_text(encoding="utf-8").strip().split()
    if not recorded:
        return None

    return recorded[0].lower()


def _sidecar_can_be_trusted(path: Path, recorded: str | None, expected: str | None) -> bool:
    """Return whether the sidecar may stand in for a full-file hash.

    Args:
        path: Artifact path.
        recorded: Sidecar digest, when one exists.
        expected: Digest required by the caller, when one was supplied.

    Returns:
        True when the sidecar equals the expected digest and is newer than the file.
    """
    if recorded is None or expected is None or recorded != expected:
        return False

    return _sidecar_is_newer(path)


def _sidecar_is_newer(path: Path) -> bool:
    """Return whether the sidecar was written after the artifact.

    Args:
        path: Artifact path.

    Returns:
        True when the sidecar's modification time is strictly later.
    """
    sidecar = Path(str(path) + ".sha256")
    try:
        return sidecar.stat().st_mtime_ns > path.stat().st_mtime_ns
    except OSError:
        return False


def _digest_ok(actual: str, recorded: str | None, expected: str | None) -> bool:
    """Return whether the file digest agrees with the sidecar and the caller.

    Args:
        actual: Digest of the bytes on disk.
        recorded: Sidecar digest, when one exists.
        expected: Digest required by the caller, when one was supplied.

    Returns:
        True when both constraints that exist are satisfied.
    """
    if recorded is not None and recorded != actual:
        return False

    return expected is None or actual == expected
