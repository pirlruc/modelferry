"""Tests for environment and constructor configuration."""

from pathlib import Path

import pytest

from model_fetcher.client import ModelFetcher
from model_fetcher.config import FetcherConfig, default_cache_dir
from model_fetcher.exceptions import ModelFetcherError


def test_token_falls_back_to_personal_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """GITLAB_TOKEN is sent as PRIVATE-TOKEN when the constructor omits a token."""
    monkeypatch.setenv("GITLAB_TOKEN", "personal-token")
    monkeypatch.setenv("CI_JOB_TOKEN", "job-token")
    config = FetcherConfig.from_environment()
    assert config.token == "personal-token"
    assert config.token_header == "PRIVATE-TOKEN"
    assert config.base_url == "https://gitlab.com"
    assert config.cache_dir == default_cache_dir().absolute()


def test_job_token_header_and_self_hosted_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI_JOB_TOKEN selects the JOB-TOKEN header and GITLAB_URL selects the host."""
    monkeypatch.setenv("CI_JOB_TOKEN", "job-token")
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.example.com/")
    config = FetcherConfig.from_environment(token="job-token")
    assert config.token_header == "JOB-TOKEN"
    assert config.base_url == "https://gitlab.example.com"


def test_server_url_and_unleash_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI_SERVER_URL and Unleash variables fill settings the constructor omits."""
    monkeypatch.setenv("CI_SERVER_URL", "https://gitlab.internal")
    monkeypatch.setenv("UNLEASH_INSTANCE_ID", "instance-1")
    monkeypatch.setenv("UNLEASH_APP_NAME", "staging")
    config = FetcherConfig.from_environment(cache_dir="~/models")
    assert config.base_url == "https://gitlab.internal"
    assert config.unleash_instance_id == "instance-1"
    assert config.unleash_app_name == "staging"
    assert config.cache_dir == Path("~/models").expanduser().absolute()


def test_invalid_configuration_is_a_library_error() -> None:
    """Bad URLs, embedded credentials, control characters, and timeouts are rejected."""
    with pytest.raises(ModelFetcherError):
        ModelFetcher(base_url="ftp://gitlab.example.com", token="test-token")

    with pytest.raises(ModelFetcherError):
        ModelFetcher(base_url="https://user:secret@gitlab.example.com", token="test-token")

    with pytest.raises(ModelFetcherError):
        ModelFetcher(token="test-token\r\nX-Injected: 1")

    with pytest.raises(ModelFetcherError):
        ModelFetcher(token="test-token", timeout=0)

    with pytest.raises(ModelFetcherError):
        ModelFetcher(token="test-token", max_bytes=0)
