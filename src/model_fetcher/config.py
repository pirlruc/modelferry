"""Authentication, host, and cache settings with environment fallback."""

import os
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

_DEFAULT_BASE_URL = "https://gitlab.com"
_DEFAULT_APP_NAME = "production"
TokenHeader = Literal["PRIVATE-TOKEN", "JOB-TOKEN"]


def default_cache_dir() -> Path:
    """Return the default on-disk cache root.

    Returns:
        ``~/.cache/model_fetcher`` expanded for the current user.
    """
    return Path.home() / ".cache" / "model_fetcher"


def _clean_url(value: str) -> str:
    """Normalize a registry base URL.

    Args:
        value: Candidate base URL.

    Returns:
        The URL without a trailing slash.

    Raises:
        ValueError: If the URL is blank or not HTTP(S).
    """
    text = value.strip().rstrip("/")
    if not text:
        raise ValueError("base_url must not be empty")

    if not text.startswith(("https://", "http://")):
        raise ValueError("base_url must start with http:// or https://")

    return text


def _resolve_token(explicit: str | None) -> tuple[str | None, TokenHeader]:
    """Choose a token and the GitLab header that should carry it.

    Constructor tokens are personal access tokens unless the value is exactly
    ``CI_JOB_TOKEN`` and ``GITLAB_TOKEN`` is unset or different. When no
    constructor token is provided, ``GITLAB_TOKEN`` wins over ``CI_JOB_TOKEN``.

    Args:
        explicit: Token passed by the caller, if any.

    Returns:
        The token value and either ``PRIVATE-TOKEN`` or ``JOB-TOKEN``.
    """
    private_token = os.environ.get("GITLAB_TOKEN") or None
    job_token = os.environ.get("CI_JOB_TOKEN") or None
    if explicit:
        if job_token and explicit == job_token and explicit != private_token:
            return explicit, "JOB-TOKEN"

        return explicit, "PRIVATE-TOKEN"

    if private_token:
        return private_token, "PRIVATE-TOKEN"

    if job_token:
        return job_token, "JOB-TOKEN"

    return None, "PRIVATE-TOKEN"


def _first_env(*names: str) -> str | None:
    """Return the first non-empty environment variable.

    Args:
        names: Environment variable names in priority order.

    Returns:
        The first non-blank value, or ``None``.
    """
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()

    return None


class FetcherConfig(BaseModel):
    """Resolved connection settings for one provider.

    Attributes:
        provider: Registry provider name, such as ``gitlab``.
        base_url: Registry origin without a trailing slash.
        token: Access token, when one is configured.
        token_header: GitLab header used to send ``token``.
        cache_dir: Root directory for cached artifacts.
        timeout: HTTP timeout in seconds applied to connect, read, and write.
        unleash_instance_id: GitLab Unleash instance id, when feature flags use it.
        unleash_app_name: Unleash app name, normally the GitLab environment name.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    base_url: str
    token: str | None
    token_header: TokenHeader
    cache_dir: Path
    timeout: float = Field(gt=0)
    unleash_instance_id: str | None = None
    unleash_app_name: str = _DEFAULT_APP_NAME

    @field_validator("provider")
    @classmethod
    def _provider_not_blank(cls, value: str) -> str:
        """Reject a blank provider name.

        Args:
            value: Provider name.

        Returns:
            The stripped provider name.

        Raises:
            ValueError: If the provider name is blank.
        """
        text = value.strip()
        if not text:
            raise ValueError("provider must not be empty")

        return text

    @field_validator("base_url")
    @classmethod
    def _base_url_http(cls, value: str) -> str:
        """Require an HTTP or HTTPS base URL.

        Args:
            value: Candidate base URL.

        Returns:
            The normalized base URL.
        """
        return _clean_url(value)

    @field_validator("cache_dir")
    @classmethod
    def _absolute_cache(cls, value: Path) -> Path:
        """Expand and absolutize the cache directory.

        Args:
            value: User or default cache path.

        Returns:
            An absolute path with ``~`` expanded.
        """
        return value.expanduser().absolute()

    @classmethod
    def from_environment(
        cls,
        *,
        provider: str = "gitlab",
        base_url: str | None = None,
        token: str | None = None,
        cache_dir: str | Path | None = None,
        timeout: float = 30.0,
        unleash_instance_id: str | None = None,
        unleash_app_name: str | None = None,
    ) -> Self:
        """Build settings from arguments, then environment variables.

        Environment fallback, in order:

        * Base URL: ``GITLAB_URL``, then ``CI_SERVER_URL``, then ``https://gitlab.com``.
        * Token: constructor ``token``, then ``GITLAB_TOKEN``, then ``CI_JOB_TOKEN``.
        * Unleash instance id: constructor value, then ``GITLAB_UNLEASH_INSTANCE_ID``,
          then ``UNLEASH_INSTANCE_ID``.
        * Unleash app name: constructor value, then ``GITLAB_UNLEASH_APP_NAME``,
          then ``UNLEASH_APP_NAME``, then ``production``.

        The default cache directory is ``~/.cache/model_fetcher``.

        Args:
            provider: Provider key passed to the client.
            base_url: Explicit registry origin.
            token: Explicit access token.
            cache_dir: Explicit cache directory.
            timeout: HTTP timeout in seconds.
            unleash_instance_id: Explicit Unleash instance id.
            unleash_app_name: Explicit Unleash application or environment name.

        Returns:
            Frozen configuration for providers and the cache.
        """
        resolved_url = base_url or _first_env("GITLAB_URL", "CI_SERVER_URL") or _DEFAULT_BASE_URL
        resolved_token, header = _resolve_token(token)
        resolved_cache = Path(cache_dir) if cache_dir is not None else default_cache_dir()
        resolved_instance = unleash_instance_id or _first_env(
            "GITLAB_UNLEASH_INSTANCE_ID",
            "UNLEASH_INSTANCE_ID",
        )
        resolved_app = (
            unleash_app_name
            or _first_env("GITLAB_UNLEASH_APP_NAME", "UNLEASH_APP_NAME")
            or _DEFAULT_APP_NAME
        )
        return cls(
            provider=provider,
            base_url=resolved_url,
            token=resolved_token,
            token_header=header,
            cache_dir=resolved_cache,
            timeout=timeout,
            unleash_instance_id=resolved_instance,
            unleash_app_name=resolved_app,
        )
