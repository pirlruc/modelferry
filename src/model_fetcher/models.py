"""Public data models for coordinates, flag evaluation, and downloads."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _required_text(value: str) -> str:
    """Reject blank coordinate fields.

    Args:
        value: Raw field value.

    Returns:
        The same value when it contains non-whitespace characters.

    Raises:
        ValueError: If the value is empty or whitespace.
    """
    if not value.strip():
        raise ValueError("must not be empty")

    return value


class ModelCoordinates(BaseModel):
    """Identity of one model artifact in a remote registry.

    Attributes:
        project_id: Registry project id or URL path, such as ``42`` or ``group/app``.
        model_name: Model or generic package name.
        version: Model version or generic package version.
        file_name: Artifact file name. Empty when the registry must choose the only file.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str
    model_name: str
    version: str
    file_name: str | None = None

    @field_validator("project_id", "model_name", "version")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        """Reject blank coordinate fields.

        Args:
            value: Raw field value.

        Returns:
            The original value when it is not blank.
        """
        return _required_text(value)

    @field_validator("file_name")
    @classmethod
    def _blank_file_name(cls, value: str | None) -> str | None:
        """Treat a blank file name as missing.

        Args:
            value: Optional artifact file name.

        Returns:
            The stripped file name, or ``None`` when it was blank.
        """
        if value is None:
            return None

        stripped = value.strip()
        if not stripped:
            return None

        return stripped


class FeatureFlagResolution(BaseModel):
    """Result of evaluating one feature flag for model coordinates.

    Attributes:
        flag_name: Flag that was evaluated.
        is_enabled: Whether the flag is active for the supplied context.
        resolved_model: Coordinates extracted from the flag payload, if any.
        raw_payload: Provider response used to produce this resolution.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    flag_name: str
    is_enabled: bool
    resolved_model: ModelCoordinates | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("flag_name")
    @classmethod
    def _reject_blank_flag(cls, value: str) -> str:
        """Reject a blank flag name.

        Args:
            value: Raw flag name.

        Returns:
            The original value when it is not blank.
        """
        return _required_text(value)


class DownloadResult(BaseModel):
    """Local artifact produced by a registry provider.

    Attributes:
        local_path: Absolute or user-supplied path of the verified file.
        is_cached: True when the file was already present and valid.
        size_bytes: Size of the local file in bytes.
        sha256_hash: Lowercase hex SHA-256 digest of the file contents.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    local_path: Path
    is_cached: bool
    size_bytes: int = Field(ge=0)
    sha256_hash: str | None = None

    @field_validator("sha256_hash")
    @classmethod
    def _normalize_hash(cls, value: str | None) -> str | None:
        """Normalize a recorded digest to lowercase hex.

        Args:
            value: Optional SHA-256 digest.

        Returns:
            The lowercase digest, or ``None``.

        Raises:
            ValueError: If the digest is not 64 hexadecimal characters.
        """
        if value is None:
            return None

        text = value.strip().lower()
        if text.startswith("sha256:"):
            text = text.removeprefix("sha256:")

        if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
            raise ValueError("sha256_hash must be 64 hexadecimal characters")

        return text
