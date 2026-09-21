"""Tests for the ModelFetcher facade."""

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from model_fetcher import ModelFetcher, register_provider
from model_fetcher.base import BaseFlagProvider, BaseRegistryProvider
from model_fetcher.client import _PROVIDERS
from model_fetcher.exceptions import FeatureFlagError, ProviderNotSupportedError
from model_fetcher.models import DownloadResult, FeatureFlagResolution, ModelCoordinates
from tests.support import GitLabMock

_PAYLOAD = b"routed-model"
_DIGEST = hashlib.sha256(_PAYLOAD).hexdigest()


def _description_payload() -> str:
    """Return a flag description that carries model coordinates."""
    return json.dumps(
        {"model_name": "fraud_detector", "version": "v1.4.0", "file_name": "model.onnx"},
    )


def test_download_from_feature_flag_uses_the_payload(tmp_path: Path) -> None:
    """A flag payload selects the model version that is downloaded."""
    mock = GitLabMock()
    mock.add(
        "GET",
        "/api/v4/projects/42/feature_flags/model_route",
        json_body={
            "name": "model_route",
            "active": True,
            "description": _description_payload(),
            "strategies": [{"name": "default", "parameters": {}}],
        },
    )
    mock.add(
        "GET",
        "/api/v4/projects/42/ml/models/fraud_detector/versions/v1.4.0",
        json_body={
            "id": 9,
            "version": "v1.4.0",
            "files": [{"file_name": "model.onnx", "file_sha256": _DIGEST}],
        },
    )
    mock.add(
        "GET",
        "/api/v4/projects/42/packages/ml_models/9/files/model.onnx",
        content=_PAYLOAD,
    )
    client = mock.client()
    with client, ModelFetcher(token="test-token", cache_dir=tmp_path, client=client) as fetcher:
        path = fetcher.download_from_feature_flag(42, "model_route", context={"user_id": "alice"})

    assert path.read_bytes() == _PAYLOAD
    assert path.parts[-4:] == ("42", "fraud_detector", "v1.4.0", "model.onnx")


def test_disabled_flag_does_not_download(tmp_path: Path) -> None:
    """download_from_feature_flag refuses a disabled flag."""
    mock = GitLabMock()
    mock.add(
        "GET",
        "/api/v4/projects/42/feature_flags/model_route",
        json_body={"name": "model_route", "active": False, "strategies": []},
    )
    client = mock.client()
    with (
        client,
        ModelFetcher(token="test-token", cache_dir=tmp_path, client=client) as fetcher,
        pytest.raises(FeatureFlagError, match="did not resolve"),
    ):
        fetcher.download_from_feature_flag(42, "model_route")

    assert not any(path.endswith("model.onnx") for path in mock.paths())


def test_unknown_provider() -> None:
    """Unregistered provider names fail before any network call."""
    with pytest.raises(ProviderNotSupportedError, match="not registered"):
        ModelFetcher(provider="github", token="test-token")


def test_register_provider_extends_the_facade(tmp_path: Path) -> None:
    """A third-party provider can be plugged in without changing ModelFetcher."""

    class ExampleRegistry(BaseRegistryProvider):
        """Registry double used to prove the extension hook."""

        name = "example"

        def download_artifact(
            self,
            coordinates: ModelCoordinates,
            *,
            target_dir: Path | None = None,
            force_download: bool = False,
        ) -> DownloadResult:
            del force_download
            file_name = coordinates.file_name or "artifact.bin"
            root = target_dir or tmp_path
            destination = root / file_name
            destination.write_bytes(b"example")
            return DownloadResult(
                local_path=destination,
                is_cached=False,
                size_bytes=7,
                sha256_hash=hashlib.sha256(b"example").hexdigest(),
            )

        def get_version_metadata(self, coordinates: ModelCoordinates) -> dict[str, Any]:
            return {"version": coordinates.version}

    class ExampleFlags(BaseFlagProvider):
        """Flag double used to prove the extension hook."""

        name = "example"

        def evaluate_flag(
            self,
            project_id: str,
            flag_name: str,
            context: dict[str, Any] | None = None,
        ) -> FeatureFlagResolution:
            del project_id, context
            return FeatureFlagResolution(flag_name=flag_name, is_enabled=False, raw_payload={})

    register_provider("example", ExampleRegistry, ExampleFlags)
    try:
        with (
            httpx.Client() as client,
            ModelFetcher(
                provider="example",
                token="test-token",
                cache_dir=tmp_path,
                client=client,
            ) as fetcher,
        ):
            path = fetcher.download_model("1", "demo", "v1", file_name="demo.bin")

        assert path.read_bytes() == b"example"
    finally:
        del _PROVIDERS["example"]


def test_package_does_not_import_ml_frameworks() -> None:
    """The library must not load, parse, or execute models."""
    banned = {
        "joblib",
        "onnxruntime",
        "pickle",
        "sklearn",
        "tensorflow",
        "torch",
        "transformers",
    }
    root = Path(__file__).resolve().parents[1] / "src" / "model_fetcher"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".", maxsplit=1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module.split(".", maxsplit=1)[0]]

            overlap = sorted(set(modules) & banned)
            assert not overlap, f"{path} imports {overlap}"
