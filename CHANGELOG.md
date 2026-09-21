# Changelog

All notable changes to this project will be documented in this file.

Release notes are updated with [Commitizen](https://github.com/commitizen-tools/commitizen)
(`cz bump`).

## 0.1.0

### Added

- `model_fetcher.ModelFetcher` for GitLab Model Registry and Generic Package downloads.
- Feature-flag routing through the GitLab Unleash client API and the REST feature-flag API.
- Atomic local cache with SHA-256 verification.
- Provider registration so another registry can be added without changing the facade.
