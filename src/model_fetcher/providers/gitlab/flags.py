"""GitLab Unleash and REST feature-flag evaluation."""

import hashlib
import json
import logging
from typing import Any
from urllib.parse import quote

import httpx

from model_fetcher.base import BaseFlagProvider
from model_fetcher.config import FetcherConfig
from model_fetcher.exceptions import AuthenticationError, FeatureFlagError
from model_fetcher.models import FeatureFlagResolution, ModelCoordinates
from model_fetcher.providers.gitlab.http import GitLabHttp, project_path

logger = logging.getLogger(__name__)

_MODEL_NAME_KEYS = ("model_name", "modelName")
_VERSION_KEYS = ("model_version", "modelVersion", "version")
_FILE_NAME_KEYS = ("file_name", "fileName", "filename")
_PROJECT_KEYS = ("project_id", "projectId")


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
        environment = context.get("environment")
        if isinstance(environment, str) and environment:
            app_name = environment
        else:
            app_name = self._config.unleash_app_name

        instance_id = self._config.unleash_instance_id or ""
        payload = self._http.get_json(
            f"/api/v4/feature_flags/unleash/{project_path(project_id)}/client/features",
            extra_headers={
                "UNLEASH-INSTANCEID": instance_id,
                "UNLEASH-APPNAME": app_name,
            },
            require_token=False,
        )
        if payload is None:
            return None

        if not isinstance(payload, dict):
            raise FeatureFlagError("GitLab Unleash returned an unexpected payload")

        features = payload.get("features")
        if not isinstance(features, list):
            raise FeatureFlagError("GitLab Unleash response did not include features")

        for feature in features:
            if isinstance(feature, dict) and feature.get("name") == flag_name:
                return feature

        return None

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


def _resolution(
    flag: dict[str, Any],
    project_id: str,
    context: dict[str, Any],
) -> tuple[bool, ModelCoordinates | None]:
    """Decide enablement and parse the first model payload that matches context.

    Args:
        flag: Unleash feature or REST feature-flag document.
        project_id: Project used when the payload does not name one.
        context: Evaluation context.

    Returns:
        Whether the flag is enabled for the context, and coordinates when a payload
        was found on an enabled flag.
    """
    if not _flag_active(flag):
        return False, None

    strategies = _strategies(flag)
    matching = [item for item in strategies if _strategy_matches(item, context)]
    if strategies and not matching:
        return False, None

    coordinates = _coordinates_from_flag(flag, project_id, context, matching)
    return True, coordinates


def _flag_active(flag: dict[str, Any]) -> bool:
    """Return the provider's global enablement bit.

    Args:
        flag: Flag document.

    Returns:
        True when Unleash ``enabled`` or REST ``active`` is true.
    """
    if "enabled" in flag:
        return bool(flag["enabled"])

    if "active" in flag:
        return bool(flag["active"])

    return False


def _strategies(flag: dict[str, Any]) -> list[dict[str, Any]]:
    """Return strategy objects from a flag document.

    Args:
        flag: Flag document.

    Returns:
        Strategy dictionaries. Non-object entries are dropped.
    """
    raw = flag.get("strategies")
    if not isinstance(raw, list):
        return []

    return [item for item in raw if isinstance(item, dict)]


def _strategy_matches(strategy: dict[str, Any], context: dict[str, Any]) -> bool:
    """Return whether a strategy applies to the evaluation context.

    ``default`` strategies apply to every user. ``userWithId`` applies when
    ``context['user_id']`` is listed. Environment scopes must include the requested
    environment or ``*`` when the caller passed ``environment``.

    Args:
        strategy: One strategy object.
        context: Evaluation context.

    Returns:
        True when this strategy should be considered.
    """
    if not _environment_matches(strategy, context.get("environment")):
        return False

    if strategy.get("name") != "userWithId":
        return True

    user_id = context.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        return False

    parameters = strategy.get("parameters")
    raw_ids = parameters.get("userIds", "") if isinstance(parameters, dict) else ""
    allowed = {part.strip() for part in str(raw_ids).split(",") if part.strip()}
    return user_id in allowed


def _environment_matches(strategy: dict[str, Any], environment: Any) -> bool:
    """Compare a strategy's scopes with the requested environment.

    Args:
        strategy: Strategy object that may contain ``scopes``.
        environment: Requested environment name, or any other value to skip filtering.

    Returns:
        True when the strategy applies to the environment.
    """
    if not isinstance(environment, str) or not environment:
        return True

    scopes = strategy.get("scopes")
    if not isinstance(scopes, list) or not scopes:
        return True

    allowed: set[str] = set()
    for scope in scopes:
        if isinstance(scope, str):
            allowed.add(scope)
        elif isinstance(scope, dict):
            value = scope.get("environment_scope")
            if isinstance(value, str):
                allowed.add(value)

    if not allowed:
        return True

    return "*" in allowed or environment in allowed


def _coordinates_from_flag(
    flag: dict[str, Any],
    project_id: str,
    context: dict[str, Any],
    strategies: list[dict[str, Any]],
) -> ModelCoordinates | None:
    """Search variant payloads, strategy parameters, and the description.

    Args:
        flag: Flag document.
        project_id: Fallback project id.
        context: Evaluation context, including an optional ``variant`` name.
        strategies: Strategies that already matched the context.

    Returns:
        Parsed coordinates, or ``None`` when no payload describes a model.
    """
    variant = _select_variant(_variants(flag), context)
    if variant is not None:
        found = _coordinates_from_mapping(_variant_payload(variant), project_id)
        if found is not None:
            return found

    for strategy in strategies:
        parameters = strategy.get("parameters")
        found = _coordinates_from_mapping(parameters, project_id)
        if found is not None:
            return found

    return _coordinates_from_mapping(_json_object(flag.get("description")), project_id)


def _variants(flag: dict[str, Any]) -> list[dict[str, Any]]:
    """Return variant objects.

    Args:
        flag: Flag document.

    Returns:
        Variant dictionaries.
    """
    raw = flag.get("variants")
    if not isinstance(raw, list):
        return []

    return [item for item in raw if isinstance(item, dict)]


def _select_variant(
    variants: list[dict[str, Any]],
    context: dict[str, Any],
) -> dict[str, Any] | None:
    """Pick a variant by name or by a stable weight bucket.

    An explicit ``context['variant']`` selects that variant name. Otherwise a single
    variant is used. Multiple variants are weighted with SHA-256 of ``user_id`` so
    the same user stays on the same payload. Unleash weights normally sum to 1000.

    Args:
        variants: Variant objects from the flag.
        context: Evaluation context.

    Returns:
        The chosen variant, or ``None`` when the list is empty or the name is unknown.
    """
    if not variants:
        return None

    requested = context.get("variant")
    if isinstance(requested, str) and requested:
        return next((variant for variant in variants if variant.get("name") == requested), None)

    if len(variants) == 1:
        return variants[0]

    weights = [_variant_weight(variant) for variant in variants]
    total = sum(weights)
    if total <= 0:
        return variants[0]

    seed = context.get("user_id")
    seed_text = seed if isinstance(seed, str) and seed else "anonymous"
    bucket = int(hashlib.sha256(seed_text.encode()).hexdigest(), 16) % total
    cursor = 0
    chosen = variants[-1]
    for variant, weight in zip(variants, weights, strict=True):
        cursor += weight
        if bucket < cursor:
            chosen = variant
            break

    return chosen


def _variant_weight(variant: dict[str, Any]) -> int:
    """Return a variant weight, treating missing or invalid values as zero.

    Args:
        variant: Unleash variant object.

    Returns:
        A non-negative weight.
    """
    raw = variant.get("weight") or 0
    if isinstance(raw, bool) or not isinstance(raw, int | str):
        return 0

    try:
        return max(int(raw), 0)
    except ValueError:
        return 0


def _variant_payload(variant: dict[str, Any]) -> Any:
    """Return the decoded variant payload value.

    Args:
        variant: Unleash variant object.

    Returns:
        A dictionary, a raw payload value, or ``None``.
    """
    payload = variant.get("payload")
    if not isinstance(payload, dict):
        return None

    return _json_object(payload.get("value")) or payload.get("value")


def _coordinates_from_mapping(value: Any, project_id: str) -> ModelCoordinates | None:
    """Build coordinates from a mapping or a JSON object string.

    Args:
        value: Candidate payload.
        project_id: Fallback project id.

    Returns:
        Coordinates when both a model name and a version are present.
    """
    data = value if isinstance(value, dict) else _json_object(value)
    if not isinstance(data, dict):
        return None

    nested = data.get("model")
    if isinstance(nested, dict):
        found = _coordinates_from_mapping(nested, project_id)
        if found is not None:
            return found

    model_name = _first_text(data, _MODEL_NAME_KEYS)
    version = _first_text(data, _VERSION_KEYS)
    if model_name is None or version is None:
        payload = data.get("payload")
        if payload is not None and payload is not value:
            return _coordinates_from_mapping(payload, project_id)

        return None

    file_name = _first_text(data, _FILE_NAME_KEYS)
    resolved_project = _first_text(data, _PROJECT_KEYS) or project_id
    try:
        return ModelCoordinates(
            project_id=resolved_project,
            model_name=model_name,
            version=version,
            file_name=file_name,
        )
    except ValueError:
        logger.debug("Ignoring feature-flag payload that failed validation")
        return None


def _json_object(value: Any) -> dict[str, Any] | None:
    """Parse a JSON object string.

    Args:
        value: Candidate JSON text or other value.

    Returns:
        The object, or ``None`` when the value is not a JSON object.
    """
    if isinstance(value, dict):
        return value

    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text.startswith("{"):
        return None

    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return None

    if isinstance(loaded, dict):
        return loaded

    return None


def _first_text(data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """Return the first non-blank string among ``keys``.

    Args:
        data: Mapping to read.
        keys: Candidate field names in priority order.

    Returns:
        The stripped string, or ``None``.
    """
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

        if isinstance(value, int) and not isinstance(value, bool) and key in _PROJECT_KEYS:
            return str(value)

    return None
