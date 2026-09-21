"""Tests for the GitLab model and generic package downloader."""

import hashlib
from pathlib import Path

import httpx
import pytest

from model_fetcher import ModelFetcher
from model_fetcher.exceptions import AuthenticationError, DownloadError, ModelNotFoundError
from tests.support import GitLabMock

_PAYLOAD = b"model-bytes"
_DIGEST = hashlib.sha256(_PAYLOAD).hexdigest()
_VERSION = "/api/v4/projects/42/ml/models/fraud/versions/v1"
_FILE = "/api/v4/projects/42/packages/ml_models/7/files/model.onnx"
_GENERIC = "/api/v4/projects/42/packages/generic/fraud/v1/model.onnx"


def _version_document() -> dict[str, object]:
    return {
        "id": 7,
        "version": "v1",
        "files": [{"file_name": "model.onnx", "file_sha256": _DIGEST}],
    }


def _fetcher(
    mock: GitLabMock,
    tmp_path: Path,
    *,
    token: str | None = "test-token",
) -> tuple[httpx.Client, ModelFetcher]:
    client = mock.client()
    fetcher = ModelFetcher(token=token, cache_dir=tmp_path, client=client)
    return client, fetcher


def test_model_registry_download_and_cache_hit(tmp_path: Path) -> None:
    """A cached artifact is returned without a second file download."""
    mock = GitLabMock()
    mock.add("GET", _VERSION, json_body=_version_document())
    mock.add("GET", _FILE, content=_PAYLOAD)
    client, fetcher = _fetcher(mock, tmp_path)
    with client, fetcher:
        first = fetcher.download_model(42, "fraud", "v1", file_name="model.onnx")
        calls_after_first = len(mock.calls)
        second = fetcher.download_model(42, "fraud", "v1", file_name="model.onnx")

    assert first == second
    assert first.read_bytes() == _PAYLOAD
    assert first == tmp_path / "gitlab" / "42" / "fraud" / "v1" / "model.onnx"
    assert len(mock.calls) == calls_after_first
    assert mock.header(0, "private-token") == "test-token"
    assert _FILE in mock.paths()


def test_force_download_fetches_again(tmp_path: Path) -> None:
    """force_download bypasses a valid cache entry."""
    mock = GitLabMock()
    mock.add("GET", _VERSION, json_body=_version_document())
    mock.add("GET", _FILE, content=_PAYLOAD)
    client, fetcher = _fetcher(mock, tmp_path)
    with client, fetcher:
        fetcher.download_model(42, "fraud", "v1", file_name="model.onnx")
        fetcher.download_model(42, "fraud", "v1", file_name="model.onnx", force_download=True)

    assert mock.paths().count(_FILE) == 2


def test_generic_package_fallback_and_project_path(tmp_path: Path) -> None:
    """A missing model version falls back to the generic package registry."""
    mock = GitLabMock()
    encoded = "/api/v4/projects/group%2Fapp/packages/generic/fraud/v1/model.onnx"
    mock.add("GET", encoded, content=_PAYLOAD)
    client, fetcher = _fetcher(mock, tmp_path)
    with client, fetcher:
        path = fetcher.download_model("group/app", "fraud", "v1", file_name="model.onnx")

    assert path.read_bytes() == _PAYLOAD
    assert encoded in mock.paths()


def test_version_lookup_by_name_then_download(tmp_path: Path) -> None:
    """Name-based model and version lists resolve the numeric package id."""
    mock = GitLabMock()
    mock.add("GET", "/api/v4/projects/42/ml/models", json_body=[{"id": 3, "name": "fraud"}])
    mock.add(
        "GET",
        "/api/v4/projects/42/ml/models/3/versions",
        json_body=[{"id": 7, "version": "v1"}],
    )
    mock.add("GET", _FILE, content=_PAYLOAD)
    client, fetcher = _fetcher(mock, tmp_path)
    with client, fetcher:
        path = fetcher.download_model(42, "fraud", "v1", file_name="model.onnx")

    assert path.is_file()
    assert _VERSION not in mock.paths() or mock.paths().count(_VERSION) == 1


def test_multiple_files_require_a_file_name(tmp_path: Path) -> None:
    """Versions with several artifacts do not guess a file."""
    mock = GitLabMock()
    mock.add(
        "GET",
        _VERSION,
        json_body={
            "id": 7,
            "version": "v1",
            "files": [{"file_name": "a.onnx"}, {"file_name": "b.onnx"}],
        },
    )
    client, fetcher = _fetcher(mock, tmp_path)
    with client, fetcher, pytest.raises(DownloadError, match="multiple files"):
        fetcher.download_model(42, "fraud", "v1")

    assert _FILE not in mock.paths()


def test_checksum_mismatch_raises_and_writes_nothing(tmp_path: Path) -> None:
    """A registry digest that does not match the body is a download error."""
    mock = GitLabMock()
    mock.add(
        "GET",
        _VERSION,
        json_body={
            "id": 7,
            "version": "v1",
            "files": [{"file_name": "model.onnx", "file_sha256": "ab" * 32}],
        },
    )
    mock.add("GET", _FILE, content=_PAYLOAD)
    client, fetcher = _fetcher(mock, tmp_path)
    with client, fetcher, pytest.raises(DownloadError, match="SHA-256 mismatch"):
        fetcher.download_model(42, "fraud", "v1")

    assert not (tmp_path / "gitlab" / "42" / "fraud" / "v1" / "model.onnx").exists()


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, AuthenticationError), (403, AuthenticationError), (404, ModelNotFoundError)],
)
def test_registry_http_errors(tmp_path: Path, status: int, error: type[Exception]) -> None:
    """401 and 403 are authentication errors and 404 is a missing model."""
    mock = GitLabMock()
    mock.add("GET", _VERSION, status=status, json_body={"message": "denied"})
    mock.add("GET", "/api/v4/projects/42/ml/models", status=status, json_body={"message": "denied"})
    mock.add("GET", _GENERIC, status=status, json_body={"message": "denied"})
    client, fetcher = _fetcher(mock, tmp_path)
    with client, fetcher, pytest.raises(error):
        fetcher.download_model(42, "fraud", "v1", file_name="model.onnx")


def test_job_token_header(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A token equal to CI_JOB_TOKEN is sent as JOB-TOKEN."""
    monkeypatch.setenv("CI_JOB_TOKEN", "job-secret")
    mock = GitLabMock()
    mock.add("GET", _VERSION, json_body=_version_document())
    mock.add("GET", _FILE, content=_PAYLOAD)
    client = mock.client()
    with (
        client,
        ModelFetcher(
            token="job-secret",
            cache_dir=tmp_path,
            client=client,
        ) as fetcher,
    ):
        fetcher.download_model(42, "fraud", "v1", file_name="model.onnx")

    assert mock.header(0, "job-token") == "job-secret"
    assert mock.header(0, "private-token") is None


def test_missing_token_is_an_authentication_error(tmp_path: Path) -> None:
    """Downloads require a token before any request is sent."""
    mock = GitLabMock()
    client, fetcher = _fetcher(mock, tmp_path, token=None)
    with client, fetcher, pytest.raises(AuthenticationError, match="token is missing"):
        fetcher.download_model(42, "fraud", "v1", file_name="model.onnx")

    assert not mock.calls
