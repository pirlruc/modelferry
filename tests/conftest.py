"""Shared pytest fixtures."""

import pytest

_GITLAB_ENV = (
    "GITLAB_TOKEN",
    "CI_JOB_TOKEN",
    "GITLAB_URL",
    "CI_SERVER_URL",
    "GITLAB_UNLEASH_INSTANCE_ID",
    "UNLEASH_INSTANCE_ID",
    "GITLAB_UNLEASH_APP_NAME",
    "UNLEASH_APP_NAME",
)


@pytest.fixture(autouse=True)
def _clear_gitlab_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove GitLab credentials so tests do not inherit the developer environment."""
    for name in _GITLAB_ENV:
        monkeypatch.delenv(name, raising=False)
