"""Branches the happy-path tests do not reach.

These cases exist so statement and branch coverage stay at the org floors.
"""

# pylint: disable=duplicate-code

import hashlib
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from model_fetcher import ModelFetcher
from model_fetcher.cache import CacheManager
from model_fetcher.client import _require_project_override
from model_fetcher.exceptions import (
    AuthenticationError,
    DownloadError,
    FeatureFlagError,
    ModelNotFoundError,
)
from model_fetcher.models import DownloadResult, ModelCoordinates
from model_fetcher.providers.gitlab.flag_eval import (
    _build_coordinates,
    _json_object,
    _strategy_rule,
    _variant_at_bucket,
    _variant_payload,
    _variant_weight,
    _weighted_variant,
)
from model_fetcher.providers.gitlab.http import _MAX_PAGES
from model_fetcher.providers.gitlab.registry import GitLabRegistryProvider
from tests.support import GitLabMock, open_fetcher

_PAYLOAD = b"model-bytes"
_DIGEST = hashlib.sha256(_PAYLOAD).hexdigest()
_VERSION = "/api/v4/projects/42/ml/models/fraud/versions/v1"
_FILE = "/api/v4/projects/42/packages/ml_models/7/files/model.onnx"
_MODELS = "/api/v4/projects/42/ml/models"
_PACKAGES = "/api/v4/projects/42/packages"
_REST = "/api/v4/projects/42/feature_flags/model_route"
_UNLEASH = "/api/v4/feature_flags/unleash/42/client/features"


def _chunks(*parts: bytes) -> Iterator[bytes]:
    yield from parts


def _fetcher(mock: GitLabMock, tmp_path: Path) -> tuple[httpx.Client, ModelFetcher]:
    client = mock.client()
    return client, ModelFetcher(token="test-token", cache_dir=tmp_path, client=client)


def test_pagination_limits_and_generic_fallback(tmp_path: Path) -> None:
    """A repeating next-page header fails, and a short list still falls back."""
    pages = GitLabMock()
    pages.add(
        "GET", _VERSION, status=404, json_body={"message": ["missing", {"id": 1}]}
    )
    for index in range(_MAX_PAGES):
        body: list[dict[str, object]] = (
            [{"id": 3, "name": "other"}] if index == 0 else []
        )
        pages.push(
            "GET", _MODELS, json_body=body, headers={"x-next-page": str(index + 2)}
        )

    client, fetcher = _fetcher(pages, tmp_path)
    with client, fetcher, pytest.raises(DownloadError, match="pagination exceeded"):
        fetcher.download_model(42, "fraud", "v1", file_name="model.onnx")

    invalid_page = GitLabMock()
    invalid_page.add("GET", _VERSION, status=404)
    invalid_page.add("GET", _MODELS, json_body=[], headers={"x-next-page": "next"})
    client, fetcher = _fetcher(invalid_page, tmp_path / "invalid-page")
    with client, fetcher, pytest.raises(DownloadError, match="x-next-page"):
        fetcher.download_model(42, "fraud", "v1", file_name="model.onnx")

    zero_page = GitLabMock()
    zero_page.add("GET", _VERSION, status=404)
    zero_page.add("GET", _MODELS, json_body=[], headers={"x-next-page": "0"})
    client, fetcher = _fetcher(zero_page, tmp_path / "zero-page")
    with client, fetcher, pytest.raises(DownloadError, match="x-next-page"):
        fetcher.download_model(42, "fraud", "v1", file_name="model.onnx")

    stuck = GitLabMock()
    stuck.add("GET", _VERSION, status=404)
    stuck.add("GET", _MODELS, json_body=[], headers={"x-next-page": "1"})
    client, fetcher = _fetcher(stuck, tmp_path / "stuck-page")
    with client, fetcher, pytest.raises(DownloadError, match="did not advance"):
        fetcher.download_model(42, "fraud", "v1", file_name="model.onnx")

    fallback = GitLabMock()
    fallback.add(
        "GET", _VERSION, status=404, json_body={"message": ["missing", {"id": 1}]}
    )
    fallback.add("GET", _MODELS, json_body=[{"id": 3, "name": "fraud"}])
    fallback.add(
        "GET",
        "/api/v4/projects/42/ml/models/3/versions",
        json_body=[{"version": "v1"}, {"id": 7, "version": "v1"}],
    )
    fallback.add("GET", _FILE, status=404, json_body={"error": {"nested": True}})
    fallback.add(
        "GET",
        "/api/v4/projects/42/packages/generic/fraud/v1/model.onnx",
        content=_PAYLOAD,
        headers={"x-checksum-sha256": _DIGEST},
    )
    client, fetcher = _fetcher(fallback, tmp_path / "fallback")
    with client, fetcher:
        saved = fetcher.download_model(42, "fraud", "v1", file_name="model.onnx")

    assert saved.read_bytes() == _PAYLOAD


def test_remaining_registry_and_http_branches(tmp_path: Path) -> None:
    """Cover error-body shapes that the happy path does not hit."""
    absent = GitLabMock()
    absent.add("GET", _VERSION, status=404, content=b"not-json")
    absent.add("GET", _MODELS, json_body=[{"id": 3, "name": "other"}])
    client, fetcher = _fetcher(absent, tmp_path / "absent")
    with client, fetcher, pytest.raises(ModelNotFoundError, match="Model"):
        fetcher.download_model(42, "fraud", "v1")

    no_version = GitLabMock()
    no_version.add("GET", _VERSION, status=500, json_body={"message": ["missing", 2]})
    no_version.add("GET", _MODELS, json_body={"not": "a list"})
    client, fetcher = _fetcher(no_version, tmp_path / "no-version")
    with client, fetcher, pytest.raises(DownloadError):
        fetcher.download_model(42, "fraud", "v1", file_name="model.onnx")

    not_list = GitLabMock()
    not_list.add("GET", _VERSION, status=404, json_body={"message": "missing"})
    not_list.add("GET", _MODELS, json_body={"not": "a list"})
    client, fetcher = _fetcher(not_list, tmp_path / "not-list")
    with client, fetcher, pytest.raises(DownloadError, match="JSON list"):
        fetcher.download_model(42, "fraud", "v1", file_name="model.onnx")

    denied = GitLabMock()
    denied.add("GET", _VERSION, json_body={"id": 7, "version": "v1", "files": "nope"})
    denied.add("GET", _FILE, status=401, json_body={"message": "nope"})
    client, fetcher = _fetcher(denied, tmp_path / "denied")
    with client, fetcher, pytest.raises(AuthenticationError):
        fetcher.download_model(42, "fraud", "v1", file_name="model.onnx")


def test_package_file_gaps_and_stream_failure(tmp_path: Path) -> None:
    """Empty package listings and a failed stream are download errors."""
    mock = GitLabMock()
    mock.add("GET", _VERSION, json_body={"id": 7, "version": "v1"})
    mock.add("GET", _PACKAGES, json_body=[{"id": 9}])
    mock.add("GET", "/api/v4/projects/42/packages/9/package_files", json_body=[])
    client, fetcher = _fetcher(mock, tmp_path)
    with client, fetcher, pytest.raises(DownloadError, match="no files"):
        fetcher.download_model(42, "fraud", "v1")

    offline_file = GitLabMock()
    offline_file.add("GET", _VERSION, json_body={"id": 7, "version": "v1"})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("model.onnx"):
            raise httpx.ConnectError("stream down")

        return offline_file.handler(request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with (
        client,
        ModelFetcher(token="test-token", cache_dir=tmp_path, client=client) as fetcher,
    ):
        with pytest.raises(DownloadError, match="failed"):
            fetcher.download_model(42, "fraud", "v1", file_name="model.onnx")

        registry = fetcher.registry
        assert isinstance(registry, GitLabRegistryProvider)
        with pytest.raises(ModelNotFoundError):
            registry._download_generic(  # pylint: disable=protected-access
                _coordinates_without_file(),
                target_dir=None,
            )


def test_cache_without_sidecar_and_optional_digest(tmp_path: Path) -> None:
    """A finished file with no sidecar or expected digest is not reused."""
    cache = CacheManager(tmp_path)
    destination = tmp_path / "plain.onnx"
    destination.write_bytes(_PAYLOAD)
    assert cache.lookup(destination) is None
    result = DownloadResult(
        local_path=destination, is_cached=True, size_bytes=1, sha256_hash=None
    )
    assert result.sha256_hash is None


def test_unleash_miss_without_a_token_returns_not_found(tmp_path: Path) -> None:
    """An Unleash miss cannot fall back to REST when no token is configured."""
    mock = GitLabMock()
    mock.add("GET", _UNLEASH, json_body={"features": [{"name": "other"}]})
    with (
        open_fetcher(mock, tmp_path, token=None) as fetcher,
        pytest.raises(FeatureFlagError, match="was not found"),
    ):
        fetcher.get_feature_flag(42, "model_route")


def test_parser_fallthroughs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defensive parser branches stay covered without a live GitLab."""
    assert _weighted_variant(
        [{"name": "a", "weight": 0}, {"name": "b", "weight": "no"}], None
    )
    assert _variant_weight({"weight": "no"}) == 0
    assert _variant_at_bucket([{"name": "a"}], [1], 5)["name"] == "a"
    assert _variant_payload({"payload": "raw"}) is None
    assert _variant_payload({"payload": {"value": "plain-text"}}) == "plain-text"
    monkeypatch.setattr(
        "model_fetcher.providers.gitlab.flag_eval.json.loads",
        lambda _text: ["not", "object"],
    )
    assert _json_object('{"model_name": "m"}') is None
    assert _build_coordinates({"project_id": "42"}, "42", "  ", "v1") is None
    assert _strategy_rule({"name": "default"}, {}) is True
    assert _strategy_rule({"name": "remoteAddress"}, {}) is False
    _require_project_override("42", "42", ())
    with pytest.raises(FeatureFlagError, match="allow list"):
        _require_project_override("42", "99", ())
    _require_project_override("42", "99", ("99",))


def _coordinates_without_file() -> ModelCoordinates:
    return ModelCoordinates(project_id="42", model_name="fraud", version="v1")


def _offline(_request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("offline")
