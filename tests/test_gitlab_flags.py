"""Tests for GitLab Unleash and REST feature-flag parsing."""

import json
from pathlib import Path

import pytest

from model_fetcher import ModelFetcher
from model_fetcher.exceptions import AuthenticationError, FeatureFlagError
from tests.support import GitLabMock

_UNLEASH = "/api/v4/feature_flags/unleash/42/client/features"
_REST = "/api/v4/projects/42/feature_flags/model_route"


def _variant_flag(payload: dict[str, object], *, enabled: bool = True) -> dict[str, object]:
    return {
        "version": 1,
        "features": [
            {
                "name": "model_route",
                "enabled": enabled,
                "strategies": [{"name": "default", "parameters": {}}],
                "variants": [
                    {
                        "name": "current",
                        "weight": 1000,
                        "payload": {"type": "json", "value": json.dumps(payload)},
                    },
                ],
            },
        ],
    }


def test_unleash_variant_payload_resolves_coordinates(tmp_path: Path) -> None:
    """A JSON variant payload becomes model coordinates."""
    mock = GitLabMock()
    mock.add(
        "GET",
        _UNLEASH,
        json_body=_variant_flag(
            {"model_name": "fraud_detector", "version": "v1.4.0", "file_name": "model.onnx"},
        ),
    )
    client = mock.client()
    with (
        client,
        ModelFetcher(
            token="test-token",
            cache_dir=tmp_path,
            client=client,
            unleash_instance_id="instance-1",
        ) as fetcher,
    ):
        resolution = fetcher.get_feature_flag(42, "model_route", context={"user_id": "alice"})

    assert resolution.is_enabled is True
    assert resolution.resolved_model is not None
    assert resolution.resolved_model.model_name == "fraud_detector"
    assert resolution.resolved_model.version == "v1.4.0"
    assert resolution.resolved_model.file_name == "model.onnx"
    assert mock.header(0, "unleash-instanceid") == "instance-1"
    assert mock.header(0, "unleash-appname") == "production"


def test_rest_strategy_payload_and_environment_scope(tmp_path: Path) -> None:
    """REST strategy parameters supply coordinates when the environment matches."""
    mock = GitLabMock()
    mock.add(
        "GET",
        _REST,
        json_body={
            "name": "model_route",
            "active": True,
            "strategies": [
                {
                    "name": "default",
                    "parameters": {"model_name": "fraud_detector", "version": "v1.4.0"},
                    "scopes": [{"environment_scope": "staging"}],
                },
            ],
        },
    )
    client = mock.client()
    with client, ModelFetcher(token="test-token", cache_dir=tmp_path, client=client) as fetcher:
        matched = fetcher.get_feature_flag(42, "model_route", context={"environment": "staging"})
        missed = fetcher.get_feature_flag(
            42,
            "model_route",
            context={"environment": "production"},
        )

    assert matched.is_enabled is True
    assert matched.resolved_model is not None
    assert matched.resolved_model.version == "v1.4.0"
    assert missed.is_enabled is False
    assert missed.resolved_model is None
    assert mock.header(0, "unleash-instanceid") is None


def test_user_strategy_filters_the_payload(tmp_path: Path) -> None:
    """userWithId strategies apply only to the listed users."""
    mock = GitLabMock()
    mock.add(
        "GET",
        _REST,
        json_body={
            "name": "model_route",
            "active": True,
            "strategies": [
                {
                    "name": "userWithId",
                    "parameters": {
                        "userIds": "alice,bob",
                        "model_name": "fraud_detector",
                        "version": "v2",
                    },
                },
            ],
        },
    )
    client = mock.client()
    with client, ModelFetcher(token="test-token", cache_dir=tmp_path, client=client) as fetcher:
        allowed = fetcher.get_feature_flag(42, "model_route", context={"user_id": "bob"})
        blocked = fetcher.get_feature_flag(42, "model_route", context={"user_id": "carol"})

    assert allowed.resolved_model is not None
    assert allowed.resolved_model.version == "v2"
    assert blocked.is_enabled is False


def test_disabled_and_missing_flags(tmp_path: Path) -> None:
    """A disabled flag returns no model and a missing flag is an error."""
    mock = GitLabMock()
    mock.add(
        "GET",
        _REST,
        json_body={
            "name": "model_route",
            "active": False,
            "strategies": [
                {"name": "default", "parameters": {"model_name": "fraud", "version": "v1"}},
            ],
        },
    )
    client = mock.client()
    with client, ModelFetcher(token="test-token", cache_dir=tmp_path, client=client) as fetcher:
        disabled = fetcher.get_feature_flag(42, "model_route")
        with pytest.raises(FeatureFlagError, match="was not found"):
            fetcher.get_feature_flag(42, "missing")

    assert disabled.is_enabled is False
    assert disabled.resolved_model is None


def test_unleash_without_private_token(tmp_path: Path) -> None:
    """Unleash evaluation uses the instance id and does not require a personal token."""
    mock = GitLabMock()
    mock.add(
        "GET",
        _UNLEASH,
        json_body=_variant_flag({"model_name": "fraud_detector", "version": "v9"}),
    )
    client = mock.client()
    with (
        client,
        ModelFetcher(
            cache_dir=tmp_path,
            client=client,
            unleash_instance_id="instance-1",
            unleash_app_name="staging",
        ) as fetcher,
    ):
        resolution = fetcher.get_feature_flag(42, "model_route", context={"environment": "qa"})
        with pytest.raises(FeatureFlagError, match="header value"):
            fetcher.get_feature_flag(42, "model_route", context={"environment": "qa\r\nX: 1"})

    assert resolution.resolved_model is not None
    assert resolution.resolved_model.version == "v9"
    assert mock.header(0, "private-token") is None
    assert mock.header(0, "unleash-appname") == "qa"


def test_gradual_rollout_percentage(tmp_path: Path) -> None:
    """A zero percent rollout does not resolve, and 100 percent does for a user."""

    def flag(percentage: str) -> dict[str, object]:
        return {
            "name": "model_route",
            "active": True,
            "strategies": [
                {
                    "name": "gradualRolloutUserId",
                    "parameters": {"percentage": percentage, "groupId": "model_route"},
                },
            ],
            "description": '{"model_name": "fraud", "version": "v1"}',
        }

    mock = GitLabMock()
    mock.push("GET", _REST, json_body=flag("0"))
    mock.push("GET", _REST, json_body=flag("100"))
    mock.add("GET", _REST, json_body=flag("100"))
    client = mock.client()
    with client, ModelFetcher(token="test-token", cache_dir=tmp_path, client=client) as fetcher:
        blocked = fetcher.get_feature_flag(42, "model_route", context={"user_id": "alice"})
        allowed = fetcher.get_feature_flag(42, "model_route", context={"user_id": "alice"})
        anonymous = fetcher.get_feature_flag(42, "model_route")

    assert blocked.is_enabled is False
    assert blocked.resolved_model is None
    assert allowed.is_enabled is True
    assert allowed.resolved_model is not None
    assert anonymous.is_enabled is False


def test_flag_unauthorized(tmp_path: Path) -> None:
    """A 401 from the feature-flag API is an authentication error."""
    mock = GitLabMock()
    mock.add("GET", _REST, status=401, json_body={"message": "401 Unauthorized"})
    client = mock.client()
    with (
        client,
        ModelFetcher(token="test-token", cache_dir=tmp_path, client=client) as fetcher,
        pytest.raises(AuthenticationError),
    ):
        fetcher.get_feature_flag(42, "model_route")
