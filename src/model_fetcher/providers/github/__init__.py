"""GitHub Releases provider exports."""

from model_fetcher.providers.github.flags import GitHubFlagProvider
from model_fetcher.providers.github.registry import GitHubRegistryProvider

__all__ = ["GitHubFlagProvider", "GitHubRegistryProvider"]
