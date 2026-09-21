"""GitLab Unleash and REST feature-flag evaluation."""

from typing import Any
from urllib.parse import quote

import httpx

from model_fetcher.base import BaseFlagProvider
from model_fetcher.config import FetcherConfig
from model_fetcher.exceptions import AuthenticationError, FeatureFlagError
from model_fetcher.models import FeatureFlagResolution
from model_fetcher.providers.gitlab.flag_eval import (
    _named_feature,
    _resolution,
    _unleash_headers,
)
from model_fetcher.providers.gitlab.http import GitLabHttp, project_path


class GitLabFlagProvider(BaseFlagProvider):
    """Resolve model coordinates from a GitLab feature flag.

    When ``GITLAB_UNLEASH_INSTANCE_ID`` or ``unleash_instance_id`` is set, the
    provider reads ``GET /api/v4/feature_flags/unleash/:project_id/client/features``
    with the ``UNLEASH-INSTANCEID`` and ``UNLEASH-APPNAME`` headers. Otherwise, or
    when that flag is absent from the Unleash payload, it reads
    ``GET /api/v4/projects/:id/feature_flags/:name``.

    A model payload is a JSON object with ``model_name`` and ``version`` (or
    ``model_version``). It may live in a variant payload, in strategy parameters,
    or in the flag description. ``file_name`` and ``project_id`` are optional.
    """

    name = "gitlab"

    def __init__(self, config: FetcherConfig, client: httpx.Client) -> None:
        """Create the GitLab feature-flag provider.

        Args:
            config: Resolved GitLab settings, including the optional Unleash id.
            client: Shared HTTP client.
        """
        super().__init__(config, client)
        self._http = GitLabHttp(config, client)

    def evaluate_flag(
        self,
        project_id: str,
        flag_name: str,
        context: dict[str, Any] | None = None,
    ) -> FeatureFlagResolution:
        """Evaluate a flag and extract model coordinates when the payload has them.

        A missing flag raises :class:`FeatureFlagError`. A flag that is disabled
        for the context returns ``is_enabled=False`` and no coordinates. Callers
        that must download a model should treat that result as an error.

        Args:
            project_id: Project that owns the flag.
            flag_name: Flag name.
            context: Optional ``user_id``, ``environment``, and ``variant``.

        Returns:
            Enablement and any resolved coordinates.

        Raises:
            FeatureFlagError: If the flag does not exist.
            AuthenticationError: If GitLab or Unleash rejects the credentials.
            DownloadError: If the HTTP call fails for a non-auth reason.
        """
        evaluation_context = dict(context or {})
        flag = self._load_flag(project_id, flag_name, evaluation_context)
        if flag is None:
            raise FeatureFlagError(
                f"Feature flag {flag_name!r} was not found in project {project_id!r}",
            )

        enabled, coordinates = _resolution(flag, project_id, evaluation_context)
        return FeatureFlagResolution(
            flag_name=flag_name,
            is_enabled=enabled,
            resolved_model=coordinates,
            raw_payload=flag,
        )

    def _load_flag(
        self,
        project_id: str,
        flag_name: str,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Load the flag document from Unleash, then the REST API.

        Args:
            project_id: Project that owns the flag.
            flag_name: Flag name.
            context: Evaluation context. ``environment`` selects the Unleash app name.

        Returns:
            The flag object, or ``None`` when both sources report it missing.

        Raises:
            AuthenticationError: If a configured credential is rejected.
        """
        if self._config.unleash_instance_id:
            unleash_flag = self._load_unleash(project_id, flag_name, context)
            if unleash_flag is not None:
                return unleash_flag

        if not self._config.token:
            if self._config.unleash_instance_id:
                return None

            raise AuthenticationError(
                "GitLab feature flags need a token or an Unleash instance id.",
            )

        return self._load_rest(project_id, flag_name)

    def _load_unleash(
        self,
        project_id: str,
        flag_name: str,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Read one flag from the GitLab Unleash client API.

        Args:
            project_id: Project that owns the flag.
            flag_name: Flag name.
            context: Evaluation context used to choose ``UNLEASH-APPNAME``.

        Returns:
            The matching feature object, or ``None`` when it is absent.

        Raises:
            AuthenticationError: If the instance id is rejected.
            FeatureFlagError: If the Unleash payload is not the expected document.
        """
        payload = self._http.get_json(
            f"/api/v4/feature_flags/unleash/{project_path(project_id)}/client/features",
            extra_headers=_unleash_headers(self._config, context),
            require_token=False,
        )
        return _named_feature(payload, flag_name)

    def _load_rest(self, project_id: str, flag_name: str) -> dict[str, Any] | None:
        """Read one flag from the project feature-flag REST API.

        Args:
            project_id: Project that owns the flag.
            flag_name: Flag name.

        Returns:
            The flag object, or ``None`` on HTTP 404.

        Raises:
            FeatureFlagError: If the body is not a JSON object.
        """
        payload = self._http.get_json(
            f"/api/v4/projects/{project_path(project_id)}/feature_flags/"
            f"{quote(flag_name, safe='')}",
        )
        if payload is None:
            return None

        if not isinstance(payload, dict):
            raise FeatureFlagError("GitLab feature flag response was not a JSON object")

        return payload
