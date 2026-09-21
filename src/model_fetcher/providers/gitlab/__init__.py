"""GitLab provider exports."""

from model_fetcher.providers.gitlab.flags import GitLabFlagProvider
from model_fetcher.providers.gitlab.registry import GitLabRegistryProvider

__all__ = ["GitLabFlagProvider", "GitLabRegistryProvider"]
