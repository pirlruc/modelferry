"""Built-in registry and feature-flag providers."""

from model_fetcher.providers.gitlab import GitLabFlagProvider, GitLabRegistryProvider

__all__ = ["GitLabFlagProvider", "GitLabRegistryProvider"]
