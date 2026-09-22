"""Pure evaluation of GitLab feature-flag documents.

The provider class loads the document. This module decides whether it is enabled
and which model coordinates it names. Keeping the parsers here holds the
maintainability index of each module above the org floor.
"""

import hashlib
import json
import logging
from typing import Any, TypeGuard

from model_fetcher.config import FetcherConfig
from model_fetcher.exceptions import FeatureFlagError
from model_fetcher.models import ModelCoordinates
from model_fetcher.providers.gitlab.rollout import rollout_matches

logger = logging.getLogger(__name__)

_MODEL_NAME_KEYS = ("model_name", "modelName")
_VERSION_KEYS = ("model_version", "modelVersion", "version")
_FILE_NAME_KEYS = ("file_name", "fileName", "filename")
_PROJECT_KEYS = ("project_id", "projectId")


def _unleash_headers(config: FetcherConfig, context: dict[str, Any]) -> dict[str, str]:
    """Build the Unleash client headers for one evaluation.

    Args:
        config: Instance id and default app name.
        context: Evaluation context. ``environment`` overrides the app name.

    Returns:
        ``UNLEASH-INSTANCEID`` and ``UNLEASH-APPNAME`` values.
    """
    return {
        "UNLEASH-INSTANCEID": config.unleash_instance_id or "",
        "UNLEASH-APPNAME": _unleash_app_name(config, context.get("environment")),
    }


def _unleash_app_name(config: FetcherConfig, environment: Any) -> str:
    """Choose the Unleash app name.

    Args:
        config: Default app name.
        environment: Requested environment, when the caller passed a string.

    Returns:
        The environment name, or the configured app name.
    """
    if isinstance(environment, str) and environment:
        return _header_environment(environment)

    return config.unleash_app_name


def _header_environment(environment: str) -> str:
    """Return an environment name that is safe to send as ``UNLEASH-APPNAME``.

    Args:
        environment: Caller-supplied environment.

    Returns:
        The same environment name.

    Raises:
        FeatureFlagError: If the name contains a control character.
    """
    if any(ord(char) < 32 or ord(char) == 127 for char in environment):
        raise FeatureFlagError("Feature-flag environment is not a valid header value")

    return environment


def _named_feature(payload: Any, flag_name: str) -> dict[str, Any] | None:
    """Return the Unleash feature object with ``flag_name``.

    Args:
        payload: Decoded Unleash document, or ``None`` on HTTP 404.
        flag_name: Flag name.

    Returns:
        The matching feature, or ``None`` when the document omits it.

    Raises:
        FeatureFlagError: If the document is not a feature list.
    """
    if payload is None:
        return None

    features = _unleash_features(payload)
    return _feature_named(features, flag_name)


def _unleash_features(payload: Any) -> list[Any]:
    """Return the ``features`` list from an Unleash document.

    Args:
        payload: Decoded JSON.

    Returns:
        The feature list.

    Raises:
        FeatureFlagError: If the document is not the expected object.
    """
    if not isinstance(payload, dict):
        raise FeatureFlagError("GitLab Unleash returned an unexpected payload")

    features = payload.get("features")
    if not isinstance(features, list):
        raise FeatureFlagError("GitLab Unleash response did not include features")

    return features


def _feature_named(features: list[Any], flag_name: str) -> dict[str, Any] | None:
    """Find one feature by name.

    Args:
        features: Unleash feature objects.
        flag_name: Flag name.

    Returns:
        The matching object, or ``None``.
    """
    for feature in features:
        if isinstance(feature, dict) and feature.get("name") == flag_name:
            return feature

    return None


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
    ``context['user_id']`` is listed. ``gradualRolloutUserId`` applies when that
    user falls inside the percentage. Environment scopes must include the requested
    environment or ``*`` when the caller passed ``environment``.

    Args:
        strategy: One strategy object.
        context: Evaluation context.

    Returns:
        True when this strategy should be considered.
    """
    if not _environment_matches(strategy, context.get("environment")):
        return False

    return _strategy_rule(strategy, context)


def _strategy_rule(strategy: dict[str, Any], context: dict[str, Any]) -> bool:
    """Apply the strategy name after the environment scope has matched.

    Args:
        strategy: One strategy object.
        context: Evaluation context.

    Returns:
        True when this strategy should be considered.
    """
    name = strategy.get("name")
    if name == "userWithId":
        return _user_ids_match(strategy, context)

    if name == "gradualRolloutUserId":
        return rollout_matches(strategy, context)

    return True


def _user_ids_match(strategy: dict[str, Any], context: dict[str, Any]) -> bool:
    """Return whether ``context['user_id']`` is listed on a ``userWithId`` strategy.

    Args:
        strategy: Strategy whose parameters may contain ``userIds``.
        context: Evaluation context.

    Returns:
        True when the user id is in the comma-separated list.
    """
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

    allowed = _scope_names(scopes)
    if not allowed:
        return True

    return "*" in allowed or environment in allowed


def _scope_names(scopes: list[Any]) -> set[str]:
    """Collect environment names from Unleash scope entries.

    Args:
        scopes: Scope strings or objects with ``environment_scope``.

    Returns:
        Names that the strategy allows.
    """
    allowed: set[str] = set()
    for scope in scopes:
        name = _scope_name(scope)
        if name is not None:
            allowed.add(name)

    return allowed


def _scope_name(scope: Any) -> str | None:
    """Return one scope's environment name.

    Args:
        scope: A string or a scope object.

    Returns:
        The environment name, or ``None`` when the entry has none.
    """
    if isinstance(scope, str):
        return scope

    if isinstance(scope, dict):
        return _scope_value(scope.get("environment_scope"))

    return None


def _scope_value(value: Any) -> str | None:
    """Return ``value`` when it is a string.

    Args:
        value: Candidate environment name.

    Returns:
        The string, or ``None``.
    """
    if isinstance(value, str):
        return value

    return None


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
    if _variant_was_requested(requested):
        return _variant_by_name(variants, requested)

    if len(variants) == 1:
        return variants[0]

    return _weighted_variant(variants, context.get("user_id"))


def _variant_was_requested(requested: Any) -> TypeGuard[str]:
    """Return whether the caller named a variant.

    Args:
        requested: ``context['variant']``.

    Returns:
        True for a non-empty string.
    """
    return isinstance(requested, str) and bool(requested)


def _variant_by_name(
    variants: list[dict[str, Any]],
    requested: str,
) -> dict[str, Any] | None:
    """Return the variant with ``requested`` name.

    Args:
        variants: Variant objects from the flag.
        requested: Variant name.

    Returns:
        The matching variant, or ``None`` when the name is unknown.
    """
    return next((variant for variant in variants if variant.get("name") == requested), None)


def _weighted_variant(
    variants: list[dict[str, Any]],
    user_id: Any,
) -> dict[str, Any]:
    """Pick a variant with a stable hash bucket of ``user_id``.

    Args:
        variants: Two or more variant objects.
        user_id: Stickiness key. Missing values use ``anonymous``.

    Returns:
        The chosen variant. A non-positive weight total uses the first variant.
    """
    weights = [_variant_weight(variant) for variant in variants]
    total = sum(weights)
    if total <= 0:
        return variants[0]

    return _variant_at_bucket(variants, weights, _weight_bucket(user_id, total))


def _weight_bucket(user_id: Any, total: int) -> int:
    """Map a user id onto ``0 .. total-1``.

    Args:
        user_id: Stickiness key.
        total: Sum of variant weights.

    Returns:
        The bucket index.
    """
    seed = user_id if isinstance(user_id, str) and user_id else "anonymous"
    return int(hashlib.sha256(seed.encode()).hexdigest(), 16) % total


def _variant_at_bucket(
    variants: list[dict[str, Any]],
    weights: list[int],
    bucket: int,
) -> dict[str, Any]:
    """Return the variant whose cumulative weight covers ``bucket``.

    Args:
        variants: Variant objects in order.
        weights: Non-negative weights aligned with ``variants``.
        bucket: Index in ``0 .. sum(weights)-1``.

    Returns:
        The matching variant, or the last variant when the bucket is past the end.
    """
    cursor = 0
    for variant, weight in zip(variants, weights, strict=True):
        cursor += weight
        if bucket < cursor:
            return variant

    return variants[-1]


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

    nested = _nested_model(data, project_id)
    if nested is not None:
        return nested

    model_name = _first_text(data, _MODEL_NAME_KEYS)
    version = _first_text(data, _VERSION_KEYS)
    if model_name is None or version is None:
        return _payload_coordinates(data, project_id, value)

    return _build_coordinates(data, project_id, model_name, version)


def _nested_model(data: dict[str, Any], project_id: str) -> ModelCoordinates | None:
    """Parse a nested ``model`` object.

    Args:
        data: Payload that may contain ``model``.
        project_id: Fallback project id.

    Returns:
        Coordinates from the nested object, or ``None``.
    """
    nested = data.get("model")
    if not isinstance(nested, dict):
        return None

    return _coordinates_from_mapping(nested, project_id)


def _payload_coordinates(
    data: dict[str, Any],
    project_id: str,
    original: Any,
) -> ModelCoordinates | None:
    """Parse a nested ``payload`` that is not the object already being read.

    Args:
        data: Payload missing a direct model name or version.
        project_id: Fallback project id.
        original: Value passed to the caller, used to stop a self-cycle.

    Returns:
        Coordinates from the nested payload, or ``None``.
    """
    payload = data.get("payload")
    if payload is None or payload is original:
        return None

    return _coordinates_from_mapping(payload, project_id)


def _build_coordinates(
    data: dict[str, Any],
    project_id: str,
    model_name: str,
    version: str,
) -> ModelCoordinates | None:
    """Build coordinates from fields that already include a name and version.

    Args:
        data: Payload mapping.
        project_id: Fallback project id.
        model_name: Model name.
        version: Model version.

    Returns:
        The coordinates, or ``None`` when validation rejects them.
    """
    try:
        return ModelCoordinates(
            project_id=_first_text(data, _PROJECT_KEYS) or project_id,
            model_name=model_name,
            version=version,
            file_name=_first_text(data, _FILE_NAME_KEYS),
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
