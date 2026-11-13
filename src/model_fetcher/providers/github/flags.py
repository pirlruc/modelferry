"""Feature flags stored as JSON in a GitHub repository."""

from typing import Any
from urllib.parse import quote

import httpx

from model_fetcher.base import BaseFlagProvider
from model_fetcher.config import FetcherConfig
from model_fetcher.exceptions import DownloadError, FeatureFlagError, ModelNotFoundError
from model_fetcher.models import FeatureFlagResolution, ModelCoordinates
from model_fetcher.providers.github.http import GitHubHttp
from model_fetcher.providers.github.registry import repository_path


class GitHubFlagProvider(BaseFlagProvider):  # pylint: disable=too-few-public-methods
    """Read ``.model-fetcher/flags/<name>.json`` from the default branch.

    GitHub has no Unleash API. The file is ``{"enabled": true, "model_name":
    "...", "version": "..."}``. ``file_name`` and ``project_id`` are optional.
    """

    name = "github"

    def __init__(self, config: FetcherConfig, client: httpx.Client) -> None:
        """Create the GitHub flag provider.

        Args:
            config: Resolved GitHub settings.
            client: Shared HTTP client.
        """
        super().__init__(config, client)
        self._http = GitHubHttp(config, client)

    def evaluate_flag(
        self,
        project_id: str,
        flag_name: str,
        context: dict[str, Any] | None = None,
    ) -> FeatureFlagResolution:
        """Load one flag file and parse its model payload.

        Args:
            project_id: ``owner/repo`` that stores the flag.
            flag_name: File stem under ``.model-fetcher/flags``.
            context: Ignored. GitHub flags are not evaluated per user.

        Returns:
            Enablement and any resolved coordinates.

        Raises:
            FeatureFlagError: If the file is missing or is not a flag object.
        """
        del context
        try:
            document = self._load(project_id, flag_name)
        except ModelNotFoundError as exc:
            raise FeatureFlagError(
                f"Feature flag {flag_name!r} was not found in project {project_id!r}",
            ) from exc

        enabled = document.get("enabled")
        if not isinstance(enabled, bool):
            raise FeatureFlagError(
                f"Feature flag {flag_name!r} has no boolean enabled field"
            )
        coordinates = _coordinates(document, project_id) if enabled else None
        return FeatureFlagResolution(
            flag_name=flag_name,
            is_enabled=enabled,
            resolved_model=coordinates,
            raw_payload=document,
        )

    def _load(self, project_id: str, flag_name: str) -> dict[str, Any]:
        """GET the raw flag JSON.

        Args:
            project_id: ``owner/repo``.
            flag_name: Flag file stem.

        Returns:
            The flag object.

        Raises:
            DownloadError: If ``flag_name`` is not a single path segment.
        """
        if "/" in flag_name or flag_name in {"", ".", ".."}:
            raise DownloadError("flag_name must be a single path segment")
        repo = repository_path(project_id)
        stem = quote(flag_name, safe="")
        return self._http.get_raw_json(
            f"/repos/{repo}/contents/.model-fetcher/flags/{stem}.json",
        )


def _coordinates(document: dict[str, Any], project_id: str) -> ModelCoordinates:
    """Build coordinates from a flag payload.

    Args:
        document: Flag JSON.
        project_id: Project that owns the flag, used when the payload omits one.

    Returns:
        Coordinates for the model the flag points at.

    Raises:
        FeatureFlagError: If the payload has no model name and version.
    """
    model_name = document.get("model_name")
    version = document.get("version") or document.get("model_version")
    if not isinstance(model_name, str) or not isinstance(version, str):
        raise FeatureFlagError("Enabled flag payload needs model_name and version")
    override = document.get("project_id")
    chosen = override if isinstance(override, str) and override.strip() else project_id
    file_name = document.get("file_name")
    return ModelCoordinates(
        project_id=chosen,
        model_name=model_name,
        version=version,
        file_name=file_name if isinstance(file_name, str) else None,
    )
