<!-- markdownlint-disable MD024 -->

# Changelog

All notable changes to this project will be documented in this file.

Release notes are updated with [Commitizen](https://github.com/commitizen-tools/commitizen)
(`cz bump`).

## 0.2.0

### Added

- GitHub Releases downloads and a raw-file feature flag through `provider="github"`.
- OpenSSF Scorecard, dependency review, threshold drift, artifact sweep, and CodeQL.
- GitHub Release builds go through pydevops `python-release.yml`. Tags are bare `X.Y.Z`.

### Fixed

- A cache lookup skips a symlink, and an orphaned partial is removed when its process is gone or the file is older than an hour.
- `ModelFetcher(max_bytes=None)` leaves the download uncapped. Omitting the argument still uses 8 GiB.

## 0.1.0

### Fixed

- Pagination stops when `x-next-page` does not advance.
- A token is not sent to a non-loopback `http://` origin.
- A cache hit requires an expected digest or a matching sidecar.
- Unknown feature-flag strategies fail closed.
- A flag payload cannot switch project unless that project is on the allow list.
- Downloads default to an 8 GiB cap.

### Added

- `model_fetcher.ModelFetcher` for GitLab Model Registry and Generic Package downloads.
- Feature-flag routing through the GitLab Unleash client API and the REST feature-flag API.
- Atomic local cache with SHA-256 verification.
- Provider registration so another registry can be added without changing the facade.
