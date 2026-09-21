"""Tests for the local artifact cache."""

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from model_fetcher.cache import CacheManager, cache_segment
from model_fetcher.exceptions import DownloadError


def _chunks(*parts: bytes) -> Iterator[bytes]:
    yield from parts


def test_destination_layout_encodes_project_paths(tmp_path: Path) -> None:
    """Project paths stay one directory and cannot escape the cache root."""
    cache = CacheManager(tmp_path)
    path = cache.destination(
        provider="gitlab",
        project_id="group/app",
        model_name="fraud",
        version="v1",
        file_name="model.onnx",
    )
    assert path == tmp_path / "gitlab" / "group%2Fapp" / "fraud" / "v1" / "model.onnx"
    assert cache_segment("group/app") == "group%2Fapp"


def test_destination_rejects_parent_segments_and_nested_files(tmp_path: Path) -> None:
    """Reject path traversal in coordinates and nested file names."""
    cache = CacheManager(tmp_path)
    with pytest.raises(DownloadError):
        cache.destination(
            provider="gitlab",
            project_id="..",
            model_name="fraud",
            version="v1",
            file_name="model.onnx",
        )

    with pytest.raises(DownloadError):
        cache.destination(
            provider="gitlab",
            project_id="42",
            model_name="fraud",
            version="v1",
            file_name="nested/model.onnx",
        )


def test_write_atomic_verifies_hash_and_leaves_no_partial(tmp_path: Path) -> None:
    """A completed write replaces the temporary file and records the digest."""
    cache = CacheManager(tmp_path)
    destination = tmp_path / "gitlab" / "model.onnx"
    payload = b"model-bytes"
    expected = hashlib.sha256(payload).hexdigest()
    result = cache.write_atomic(destination, _chunks(b"model-", b"bytes"), expected_sha256=expected)
    assert result.local_path == destination
    assert result.is_cached is False
    assert result.size_bytes == len(payload)
    assert result.sha256_hash == expected
    assert destination.read_bytes() == payload
    assert not destination.with_name("model.onnx.downloading").exists()
    assert Path(str(destination) + ".sha256").read_text(encoding="utf-8").strip() == expected
    cached = cache.lookup(destination, expected_sha256=expected)
    assert cached is not None
    assert cached.is_cached is True


def test_checksum_mismatch_removes_the_partial_file(tmp_path: Path) -> None:
    """A bad digest never becomes the published artifact."""
    cache = CacheManager(tmp_path)
    destination = tmp_path / "model.onnx"
    with pytest.raises(DownloadError, match="SHA-256 mismatch"):
        cache.write_atomic(destination, _chunks(b"hello"), expected_sha256="0" * 64)

    assert not destination.exists()
    assert not destination.with_name("model.onnx.downloading").exists()


def test_size_mismatch_and_interrupted_stream_remove_partials(tmp_path: Path) -> None:
    """Incomplete streams do not leave a final artifact behind."""
    cache = CacheManager(tmp_path)
    short = tmp_path / "short.onnx"
    with pytest.raises(DownloadError, match="Incomplete download"):
        cache.write_atomic(short, _chunks(b"hello"), expected_size=99)

    assert not short.exists()

    def fail_midstream() -> Iterator[bytes]:
        yield b"abc"
        raise OSError("connection reset")

    broken = tmp_path / "broken.onnx"
    with pytest.raises(OSError, match="connection reset"):
        cache.write_atomic(broken, fail_midstream())

    assert not broken.exists()
    assert not broken.with_name("broken.onnx.downloading").exists()


def test_downloading_marker_and_sidecar_mismatch_are_cache_misses(tmp_path: Path) -> None:
    """Interrupted or corrupted files are not reused."""
    cache = CacheManager(tmp_path)
    destination = tmp_path / "model.onnx"
    destination.write_bytes(b"hello")
    destination.with_name("model.onnx.downloading").write_bytes(b"partial")
    assert cache.lookup(destination) is None

    destination.with_name("model.onnx.downloading").unlink()
    Path(str(destination) + ".sha256").write_text(f"{'ab' * 32}\n", encoding="utf-8")
    assert cache.lookup(destination) is None


def test_target_dir_places_the_file_directly(tmp_path: Path) -> None:
    """An explicit target directory skips the provider cache hierarchy."""
    cache = CacheManager(tmp_path / "cache")
    target = tmp_path / "out"
    path = cache.destination(
        provider="gitlab",
        project_id="42",
        model_name="fraud",
        version="v1",
        file_name="model.onnx",
        target_dir=target,
    )
    assert path == target / "model.onnx"
