"""GitHub Releases provider tests against a mock transport."""

import hashlib
from pathlib import Path
from typing import Any

import httpx
import pytest

from model_fetcher import ModelFetcher
from model_fetcher.exceptions import (
    AuthenticationError,
    DownloadError,
    FeatureFlagError,
    ModelNotFoundError,
)


def _release(name: str, digest: str, size: int) -> dict[str, object]:
    return {
        "tag_name": "1.0.0",
        "assets": [
            {
                "name": name,
                "digest": f"sha256:{digest}",
                "size": size,
                "url": "https://api.github.com/repos/acme/models/releases/assets/7",
            }
        ],
    }


def test_download_release_asset_verifies_the_digest(tmp_path: Path) -> None:
    """A release asset is cached only when the bytes match the GitHub digest."""
    body = b"model-bytes"
    digest = hashlib.sha256(body).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/releases/tags/1.0.0"):
            return httpx.Response(200, json=_release("fraud.onnx", digest, len(body)))
        if request.url.path.endswith("/releases/assets/7"):
            assert request.headers["authorization"] == "Bearer secret"
            return httpx.Response(200, content=body)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with ModelFetcher(
        provider="github",
        base_url="https://api.github.com",
        token="secret",
        cache_dir=tmp_path,
        client=httpx.Client(transport=transport),
    ) as fetcher:
        path = fetcher.download_model(
            "acme/models", "fraud", "1.0.0", file_name="fraud.onnx"
        )

    assert path.read_bytes() == body
    assert path.parent.name == "1.0.0"
    again = fetcher.download_model(
        "acme/models", "fraud", "1.0.0", file_name="fraud.onnx"
    )
    assert again == path
    forced = fetcher.download_model(
        "acme/models",
        "fraud",
        "1.0.0",
        file_name="fraud.onnx",
        force_download=True,
    )
    assert forced == path


def test_asset_without_a_digest_is_refused(tmp_path: Path) -> None:
    """An asset that GitHub did not digest is not stored."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "assets": [
                    {
                        "name": "fraud.onnx",
                        "size": 4,
                        "url": "https://api.github.com/repos/acme/models/releases/assets/7",
                    }
                ]
            },
        )

    with (
        ModelFetcher(
            provider="github",
            base_url="https://api.github.com",
            token="secret",
            cache_dir=tmp_path,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        ) as fetcher,
        pytest.raises(DownloadError, match="no sha256"),
    ):
        fetcher.download_model("acme/models", "fraud", "1.0.0", file_name="fraud.onnx")


def test_missing_release_is_not_found(tmp_path: Path) -> None:
    """HTTP 404 becomes ModelNotFoundError."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with (
        ModelFetcher(
            provider="github",
            base_url="https://api.github.com",
            token="secret",
            cache_dir=tmp_path,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        ) as fetcher,
        pytest.raises(ModelNotFoundError),
    ):
        fetcher.download_model("acme/models", "fraud", "9.9.9", file_name="fraud.onnx")


def test_flag_file_resolves_coordinates(tmp_path: Path) -> None:
    """A JSON flag file on the default branch selects the model."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/.model-fetcher/flags/route.json")
        return httpx.Response(
            200,
            json={
                "enabled": True,
                "model_name": "fraud",
                "version": "1.0.0",
                "file_name": "fraud.onnx",
            },
        )

    with ModelFetcher(
        provider="github",
        base_url="https://api.github.com",
        token="secret",
        cache_dir=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    ) as fetcher:
        resolution = fetcher.get_feature_flag("acme/models", "route")

    assert resolution.is_enabled is True
    assert resolution.resolved_model is not None
    assert resolution.resolved_model.version == "1.0.0"


def test_missing_flag_file(tmp_path: Path) -> None:
    """A missing flag file is a feature-flag error."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with (
        ModelFetcher(
            provider="github",
            base_url="https://api.github.com",
            token="secret",
            cache_dir=tmp_path,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        ) as fetcher,
        pytest.raises(FeatureFlagError, match="was not found"),
    ):
        fetcher.get_feature_flag("acme/models", "missing")


def _github(tmp_path: Path, handler: Any) -> ModelFetcher:
    return ModelFetcher(
        provider="github",
        base_url="https://api.github.com",
        token="secret",
        cache_dir=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_release_status_and_shape_errors(tmp_path: Path) -> None:
    """Auth, status, and malformed release payloads fail closed."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/releases/tags/auth"):
            return httpx.Response(403)
        if path.endswith("/releases/tags/missing-asset"):
            return httpx.Response(200, json={"assets": [{"name": "other.bin"}]})
        if path.endswith("/releases/tags/baddigest"):
            return httpx.Response(
                200,
                json={"assets": [{"name": "fraud.onnx", "digest": "md5:abcd"}]},
            )
        if path.endswith("/releases/tags/noassets"):
            return httpx.Response(200, json={"assets": "nope"})
        if path.endswith("/releases/tags/boom"):
            return httpx.Response(500)
        return httpx.Response(404)

    with _github(tmp_path, handler) as fetcher:
        with pytest.raises(AuthenticationError):
            fetcher.download_model(
                "acme/models", "fraud", "auth", file_name="fraud.onnx"
            )
        with pytest.raises(DownloadError, match="500"):
            fetcher.download_model(
                "acme/models", "fraud", "boom", file_name="fraud.onnx"
            )
        with pytest.raises(ModelNotFoundError, match="asset"):
            fetcher.download_model(
                "acme/models", "fraud", "missing-asset", file_name="fraud.onnx"
            )
        with pytest.raises(DownloadError, match="no sha256"):
            fetcher.download_model(
                "acme/models", "fraud", "baddigest", file_name="fraud.onnx"
            )
        with pytest.raises(ModelNotFoundError):
            fetcher.download_model(
                "acme/models", "fraud", "noassets", file_name="fraud.onnx"
            )
        with pytest.raises(DownloadError, match="owner/repo"):
            fetcher.download_model("acme", "fraud", "1.0.0", file_name="fraud.onnx")


def test_asset_url_and_model_name_download(tmp_path: Path) -> None:
    """A missing URL, an off-host URL, and a model-name asset are distinct."""
    digest = hashlib.sha256(b"data").hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/releases/tags/by-model"):
            return httpx.Response(
                200,
                json={
                    "assets": [
                        "skip",
                        {
                            "name": "fraud",
                            "digest": f"sha256:{digest}",
                            "size": 4,
                            "url": "https://api.github.com/repos/acme/models/releases/assets/9",
                        },
                    ]
                },
            )
        if path.endswith("/releases/assets/9"):
            return httpx.Response(200, content=b"data")
        if path.endswith("/releases/tags/list"):
            return httpx.Response(200, json=[])
        if path.endswith("/releases/tags/nourl"):
            return httpx.Response(
                200,
                json={
                    "assets": [
                        {
                            "name": "fraud.onnx",
                            "digest": f"sha256:{digest}",
                            "size": "4",
                        },
                    ]
                },
            )
        if path.endswith("/releases/tags/offhost"):
            return httpx.Response(
                200,
                json={
                    "assets": [
                        {
                            "name": "fraud.onnx",
                            "digest": f"sha256:{digest}",
                            "size": 1,
                            "url": "https://example.com/asset",
                        }
                    ]
                },
            )
        return httpx.Response(404)

    with _github(tmp_path, handler) as fetcher:
        with pytest.raises(DownloadError, match="not an object"):
            fetcher.download_model(
                "acme/models", "fraud", "list", file_name="fraud.onnx"
            )
        with pytest.raises(DownloadError, match="no download URL"):
            fetcher.download_model(
                "acme/models", "fraud", "nourl", file_name="fraud.onnx"
            )
        with pytest.raises(DownloadError, match="another host"):
            fetcher.download_model(
                "acme/models", "fraud", "offhost", file_name="fraud.onnx"
            )
        named = fetcher.download_model("acme/models", "fraud", "by-model")
        assert named.read_bytes() == b"data"


def test_flag_payload_errors(tmp_path: Path) -> None:
    """Flag JSON that is disabled, incomplete, or the wrong shape fails closed."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/flags/plain.json"):
            return httpx.Response(200, json={"enabled": "yes"})
        if path.endswith("/flags/off.json"):
            return httpx.Response(200, json={"enabled": False})
        if path.endswith("/flags/bare.json"):
            return httpx.Response(200, json={"enabled": True})
        if path.endswith("/flags/other.json"):
            return httpx.Response(
                200,
                json={
                    "enabled": True,
                    "model_name": "fraud",
                    "model_version": "2",
                    "project_id": "other/repo",
                },
            )
        if path.endswith("/flags/array.json"):
            return httpx.Response(200, json=[1])
        return httpx.Response(404)

    with _github(tmp_path, handler) as fetcher:
        with pytest.raises(FeatureFlagError, match="boolean"):
            fetcher.get_feature_flag("acme/models", "plain")
        disabled = fetcher.get_feature_flag("acme/models", "off")
        assert disabled.is_enabled is False
        assert disabled.resolved_model is None
        with pytest.raises(FeatureFlagError, match="model_name"):
            fetcher.get_feature_flag("acme/models", "bare")
        moved = fetcher.get_feature_flag("acme/models", "other")
        assert moved.resolved_model is not None
        assert moved.resolved_model.project_id == "other/repo"
        with pytest.raises(DownloadError, match="not a JSON object"):
            fetcher.get_feature_flag("acme/models", "array")
        with pytest.raises(DownloadError, match="single path"):
            fetcher.get_feature_flag("acme/models", "a/b")


def test_explicit_none_max_bytes_is_uncapped() -> None:
    """Omitting max_bytes keeps the default, and None removes the cap."""
    default = ModelFetcher(token="secret")
    uncapped = ModelFetcher(token="secret", max_bytes=None)
    assert default.config.max_bytes == 8 * 1024 * 1024 * 1024
    assert uncapped.config.max_bytes is None
    default.close()
    uncapped.close()
