<!-- markdownlint-disable MD024 -->

# Changelog

All notable changes to this project will be documented in this file.

Release notes are updated with [Commitizen](https://github.com/commitizen-tools/commitizen)
(`cz bump`).

## 0.4.0

### Fixed

- A GitLab redirect that leaves the API host must be HTTPS. GitHub uses the same rule.
- A GitLab download without a registry or origin SHA-256 digest is refused.
- Digest checks use a constant-time compare.
- An injected HTTP client must verify certificates and refuse TLS older than 1.2.

### Changed

- Reusable workflows pin commondevops v6.12.0.
- The security policy names a private disclosure path and a 7 day acknowledgement.

## 0.3.0

### Fixed

- GitHub release downloads follow an HTTPS redirect and drop the token when the next host is not the API.
- A token is sent to loopback HTTP only when `allow_local_http` is set. The HTTP client refuses TLS older than 1.2.

### Changed

- Reusable workflows pin commondevops v6.11.0 and pydevops 3.10.1. CodeQL and Dependabot metadata use those reusables.
- Guardrails 1.17.1 and github-scaffold 1.14.3.

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
