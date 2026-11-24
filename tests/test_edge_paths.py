"""Branches the happy-path tests do not reach.

These cases exist so statement and branch coverage stay at the org floors.
"""

import hashlib
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from model_fetcher import ModelFetcher, register_provider
from model_fetcher.cache import CacheManager, cache_segment, normalize_sha256
from model_fetcher.config import FetcherConfig
from model_fetcher.exceptions import (
    AuthenticationError,
    DownloadError,
    FeatureFlagError,
    ModelFetcherError,
    ModelNotFoundError,
)
from model_fetcher.models import DownloadResult, FeatureFlagResolution, ModelCoordinates
from model_fetcher.providers.gitlab.flag_eval import (
    _coordinates_from_mapping,
    _environment_matches,
    _feature_named,
    _named_feature,
    _resolution,
    _select_variant,
    _variant_weight,
)
from model_fetcher.providers.gitlab.flags import GitLabFlagProvider
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


def test_cache_rejects_blank_unsafe_and_invalid_digests(tmp_path: Path) -> None:
    """Path segments and digests fail closed before a file is published."""
    cache = CacheManager(tmp_path)
    with pytest.raises(DownloadError):
        cache_segment("  padded")

    with pytest.raises(DownloadError):
        cache_segment("a\\b")

    with pytest.raises(DownloadError):
        cache_segment("/abs")

    with pytest.raises(DownloadError):
        normalize_sha256("not-a-digest")

    destination = tmp_path / "model.onnx"
    with pytest.raises(DownloadError, match="empty"):
        cache.write_atomic(destination, _chunks(b"", b""))

    assert not destination.exists()
    written = cache.write_atomic(destination, _chunks(b"", _PAYLOAD))
    assert written.size_bytes == len(_PAYLOAD)
    assert cache.lookup(destination) is not None
    assert cache.lookup(destination, expected_sha256="0" * 64) is None


def test_coordinate_and_download_validators() -> None:
    """Blank fields and bad digests are rejected by the public models."""
    with pytest.raises(ValidationError):
        ModelCoordinates(project_id="  ", model_name="fraud", version="v1")

    blank_file = ModelCoordinates(
        project_id="42",
        model_name="fraud",
        version="v1",
        file_name="  ",
    )
    assert blank_file.file_name is None
    prefixed = DownloadResult(
        local_path=Path("model.onnx"),
        is_cached=False,
        size_bytes=1,
        sha256_hash="sha256:" + _DIGEST.upper(),
    )
    assert prefixed.sha256_hash == _DIGEST
    with pytest.raises(ValidationError):
        DownloadResult(
            local_path=Path("model.onnx"),
            is_cached=False,
            size_bytes=1,
            sha256_hash="zz",
        )

    with pytest.raises(ValidationError):
        FeatureFlagResolution(flag_name="  ", is_enabled=True)


def test_configuration_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment token order and rejected settings stay explicit."""
    monkeypatch.setenv("CI_JOB_TOKEN", "job-only")
    job_only = FetcherConfig.from_environment()
    assert job_only.token == "job-only"
    assert job_only.token_header == "JOB-TOKEN"

    monkeypatch.setenv("GITLAB_TOKEN", "personal")
    explicit = FetcherConfig.from_environment(token="personal-other")
    assert explicit.token_header == "PRIVATE-TOKEN"
    with pytest.raises(ValidationError):
        FetcherConfig(
            provider="  ",
            base_url="https://gitlab.example",
            token=None,
            token_header="PRIVATE-TOKEN",
            cache_dir=Path("/tmp/cache"),
            timeout=1,
        )

    with pytest.raises(ValueError, match="empty"):
        FetcherConfig.from_environment(base_url="   ")


def test_client_closes_owned_clients_and_rejects_blank_names(tmp_path: Path) -> None:
    """The facade validates coordinates and does not close an injected client."""
    with pytest.raises(ModelFetcherError, match="Provider name"):
        register_provider("  ", GitLabRegistryProvider, GitLabFlagProvider)

    owned = ModelFetcher(token="test-token", cache_dir=tmp_path)
    owned.close()
    with owned:
        pass

    mock = GitLabMock()
    client, fetcher = _fetcher(mock, tmp_path)
    with client, fetcher:
        fetcher.close()
        assert not client.is_closed
        with pytest.raises(ModelFetcherError, match="coordinates"):
            fetcher.download_model(42, "  ", "v1")


def test_registry_list_package_and_transport_edges(tmp_path: Path) -> None:
    """List fallback, package files, pagination, and bad downloads fail clearly."""
    mock = GitLabMock()
    mock.add(
        "GET",
        _VERSION,
        json_body={"id": 8, "version": "other", "files": [{"filename": "model.onnx"}]},
    )
    mock.push(
        "GET",
        _MODELS,
        json_body=[{"id": 1, "name": "other"}],
        headers={"x-next-page": "2"},
    )
    mock.add("GET", _MODELS, json_body=[{"id": 3, "name": "fraud"}, "skip"])
    mock.add(
        "GET",
        "/api/v4/projects/42/ml/models/3/versions",
        json_body=[{"id": 7, "version": "v1", "artifacts": [{"name": "model.onnx"}]}],
    )
    mock.add(
        "GET", _FILE, content=_PAYLOAD, headers={"content-length": str(len(_PAYLOAD))}
    )
    client, fetcher = _fetcher(mock, tmp_path)
    with client, fetcher:
        path = fetcher.download_model(42, "fraud", "v1")

    assert path.read_bytes() == _PAYLOAD

    empty = GitLabMock()
    empty.add("GET", _VERSION, json_body={"id": 7, "version": "v1"})
    empty.add("GET", _PACKAGES, json_body=[])
    client, fetcher = _fetcher(empty, tmp_path)
    with client, fetcher, pytest.raises(DownloadError, match="no files"):
        fetcher.download_model(42, "fraud", "v1")

    packages = GitLabMock()
    packages.add("GET", _VERSION, json_body={"id": 7, "version": "v1", "files": "nope"})
    packages.add(
        "GET",
        _PACKAGES,
        json_body=[{"id": 9}, "skip", {"no": "id"}],
    )
    packages.add(
        "GET",
        "/api/v4/projects/42/packages/9/package_files",
        json_body=[{"file_name": "model.onnx", "sha256": _DIGEST}, "skip", {}],
    )
    packages.add("GET", _FILE, content=_PAYLOAD, headers={"x-checksum-sha256": _DIGEST})
    client, fetcher = _fetcher(packages, tmp_path)
    with client, fetcher:
        listed = fetcher.download_model(42, "fraud", "v1")

    assert listed.read_bytes() == _PAYLOAD


def _offline(_request: httpx.Request) -> httpx.Response:
    """Fail the transport so the client maps it to DownloadError."""
    raise httpx.ConnectError("offline")


def test_registry_http_failures(tmp_path: Path) -> None:
    """Non-JSON bodies, HTTP 500, and transport errors become download errors."""
    mock = GitLabMock()
    mock.add("GET", _VERSION, content=b"not-json")
    mock.add("GET", _MODELS, json_body={"message": ["nope", {"x": 1}]})
    client, fetcher = _fetcher(mock, tmp_path)
    with client, fetcher, pytest.raises(DownloadError):
        fetcher.download_model(42, "fraud", "v1", file_name="model.onnx")

    broken = GitLabMock()
    broken.add("GET", _VERSION, json_body={"id": 7, "version": "v1"})
    broken.add("GET", _FILE, status=500, json_body="upstream down")
    client, fetcher = _fetcher(broken, tmp_path)
    with client, fetcher, pytest.raises(DownloadError, match="HTTP 500"):
        fetcher.download_model(42, "fraud", "v1", file_name="model.onnx")

    offline = httpx.Client(transport=httpx.MockTransport(_offline))
    with (
        offline,
        ModelFetcher(token="test-token", cache_dir=tmp_path, client=offline) as fetcher,
        pytest.raises(DownloadError, match="failed"),
    ):
        fetcher.download_model(42, "fraud", "v1", file_name="model.onnx")


def test_target_directory_skips_the_cache_tree(tmp_path: Path) -> None:
    """target_dir places the file directly and ignores a non-numeric content length."""
    mock = GitLabMock()
    mock.add("GET", _VERSION, json_body={"id": 7, "version": "v1"})
    mock.add("GET", _FILE, content=_PAYLOAD, headers={"content-length": "nope"})
    client, fetcher = _fetcher(mock, tmp_path)
    target = tmp_path / "out"
    with client, fetcher:
        saved = fetcher.download_model(
            42,
            "fraud",
            "v1",
            file_name="model.onnx",
            target_dir=target,
        )

    assert saved == target / "model.onnx"
    assert saved.read_bytes() == _PAYLOAD


def test_missing_model_without_a_file_name(tmp_path: Path) -> None:
    """A 404 with no file name does not try the generic package registry."""
    mock = GitLabMock()
    client, fetcher = _fetcher(mock, tmp_path)
    with client, fetcher, pytest.raises(ModelNotFoundError):
        fetcher.download_model(42, "fraud", "v1")


def test_flag_payload_shapes(tmp_path: Path) -> None:
    """Variant, description, and nested payloads all yield coordinates."""
    description = {
        "name": "model_route",
        "active": True,
        "description": (
            '{"model_name": "fraud", "model_version": "v3", "project_id": 7}'
        ),
    }
    nested = {
        "name": "model_route",
        "enabled": True,
        "strategies": [
            {
                "name": "default",
                "parameters": {"model": {"modelName": "fraud", "version": "v4"}},
                "scopes": ["staging", {"environment_scope": 1}, "skip-me"],
            },
        ],
    }
    weight = {
        "name": "model_route",
        "enabled": True,
        "variants": [
            {
                "name": "a",
                "weight": 0,
                "payload": {
                    "type": "json",
                    "value": {"model_name": "fraud", "version": "a"},
                },
            },
            {
                "name": "b",
                "weight": "bad",
                "payload": {"value": {"model_name": "fraud", "version": "b"}},
            },
        ],
    }
    mock = GitLabMock()
    mock.push("GET", _REST, json_body=description)
    mock.push("GET", _REST, json_body=nested)
    mock.push("GET", _REST, json_body=weight)
    mock.add("GET", _REST, json_body={"name": "model_route"})
    client, fetcher = _fetcher(mock, tmp_path)
    with client, fetcher:
        from_description = fetcher.get_feature_flag(42, "model_route")
        from_nested = fetcher.get_feature_flag(
            42,
            "model_route",
            context={"environment": "staging"},
        )
        from_weight = fetcher.get_feature_flag(
            42, "model_route", context={"variant": "b"}
        )
        inactive = fetcher.get_feature_flag(42, "model_route")

    assert from_description.resolved_model is not None
    assert from_description.resolved_model.project_id == "7"
    assert from_description.resolved_model.version == "v3"
    assert from_nested.resolved_model is not None
    assert from_nested.resolved_model.version == "v4"
    assert from_weight.resolved_model is not None
    assert from_weight.resolved_model.version == "b"
    assert inactive.is_enabled is False


def test_unleash_errors_and_missing_credentials(tmp_path: Path) -> None:
    """Bad Unleash documents and a missing credential are errors."""
    mock = GitLabMock()
    mock.push("GET", _UNLEASH, json_body=["nope"])
    mock.push("GET", _UNLEASH, json_body={"features": {}})
    mock.push("GET", _UNLEASH, json_body={"features": [{"name": "other"}]})
    mock.add("GET", _REST, json_body="not-an-object")
    with open_fetcher(mock, tmp_path, token="test-token") as fetcher:
        with pytest.raises(FeatureFlagError, match="unexpected"):
            fetcher.get_feature_flag(42, "model_route")

        with pytest.raises(FeatureFlagError, match="features"):
            fetcher.get_feature_flag(42, "model_route")

        with pytest.raises(FeatureFlagError, match="JSON object"):
            fetcher.get_feature_flag(42, "model_route")

    bare = ModelFetcher(token=None, cache_dir=tmp_path)
    with bare, pytest.raises(AuthenticationError, match="token or an Unleash"):
        bare.get_feature_flag(42, "model_route")


def test_flag_parsers_cover_remaining_shapes() -> None:
    """Pure parsers cover payload shapes the HTTP fixtures do not assemble."""
    assert _named_feature(None, "model_route") is None
    assert _feature_named(["skip", {"name": "other"}], "model_route") is None
    assert _variant_weight({"weight": True}) == 0
    assert _variant_weight({"weight": -3}) == 0
    assert _variant_weight({}) == 0
    assert _environment_matches({"scopes": [1, {}]}, "staging") is True
    assert _environment_matches({"scopes": []}, "") is True


def test_variant_selection_covers_remaining_shapes() -> None:
    """Variant selection covers weights the HTTP fixtures do not assemble."""
    chosen = _select_variant(
        [
            {"name": "a", "weight": 1},
            {"name": "b", "weight": 1},
        ],
        {"user_id": "alice"},
    )
    assert chosen is not None
    only = _select_variant([{"name": "only"}], {})
    assert only is not None
    assert only["name"] == "only"
    assert _select_variant([{"name": "only"}], {"variant": "missing"}) is None
    assert _select_variant([], {}) is None


def test_flag_resolution_covers_remaining_shapes() -> None:
    """Resolution covers payload shapes the HTTP fixtures do not assemble."""
    enabled, coordinates = _resolution(
        {
            "enabled": True,
            "strategies": "nope",
            "description": "[1, 2]",
        },
        "42",
        {},
    )
    assert enabled is True
    assert coordinates is None
    assert _coordinates_from_mapping("not-json", "42") is None
    assert _coordinates_from_mapping(
        {"payload": {"model_name": "m", "version": "v"}}, "42"
    )
    invalid = _coordinates_from_mapping({"model_name": "  ", "version": "v"}, "42")
    assert invalid is None
    user = _resolution(
        {
            "active": True,
            "strategies": [{"name": "userWithId", "parameters": "nope"}],
        },
        "42",
        {"user_id": 7},
    )
    assert user == (False, None)
