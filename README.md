# model-fetcher

`model-fetcher` (import `model_fetcher`) downloads model artifacts from a Git registry and can ask a
feature flag which model version to fetch. This repository is
[pirlruc/modelferry](https://github.com/pirlruc/modelferry).

The library has two jobs:

1. Stream a model file into a local cache, verify its SHA-256 digest, and return a `pathlib.Path`.
2. Evaluate a GitLab feature flag and read the model coordinates out of its variant or strategy
   payload.

It does not deserialize, load, or execute models. A downstream inference package receives the path
and calls its own loader.

## Install

```shell
uv add model-fetcher
```

## Direct download

```python
from model_fetcher import ModelFetcher

with ModelFetcher(base_url="https://gitlab.example.com", token="***") as fetcher:
    model_path = fetcher.download_model(
        project_id="group/models",
        model_name="fraud_detector",
        version="v1.4.0",
        file_name="model.onnx",
    )
```

`model_path` is a file under `~/.cache/model_fetcher/gitlab/<project>/<model>/<version>/`. Pass
`force_download=True` to fetch again. Pass `target_dir` to place the file somewhere else.

When `file_name` is omitted and the model version has exactly one file, that file is downloaded.
Several files require `file_name`. If the model registry has no such version, a `file_name` is
downloaded from the generic package registry instead.

## Feature-flag routing

Store a JSON payload on the flag variant or strategy:

```json
{"model_name": "fraud_detector", "version": "v1.4.0", "file_name": "model.onnx"}
```

```python
model_path = fetcher.download_from_feature_flag(
    project_id="group/models",
    flag_name="fraud_model",
    context={"user_id": "alice", "environment": "production"},
)
```

`get_feature_flag` returns the enablement bit and coordinates without downloading. A missing flag
raises `FeatureFlagError`. A disabled flag, or an enabled flag with no model payload, also raises
from `download_from_feature_flag`. A `gradualRolloutUserId` strategy includes `context["user_id"]`
only when that user's stickiness bucket falls inside the percentage.

Unleash is used when `GITLAB_UNLEASH_INSTANCE_ID` (or `unleash_instance_id=`) is set. Otherwise the
client calls the project feature-flag REST API.

## Authentication

| Source                                    | Header          |
| ----------------------------------------- | --------------- |
| `token=` or `GITLAB_TOKEN`                | `PRIVATE-TOKEN` |
| `CI_JOB_TOKEN`, when it is the only token | `JOB-TOKEN`     |

Host selection is `base_url`, then `GITLAB_URL`, then `CI_SERVER_URL`, then `https://gitlab.com`.
The same client works against GitLab.com and self-hosted instances.

## Cache

Each writer streams to its own `<name>.downloading.<pid>.<uuid>` file while holding
`<name>.lock`, then renames the file only after the byte count and SHA-256 digest match. A cache
hit whose sidecar already equals the expected digest is returned without hashing the file again.
`max_bytes=` rejects a larger body and leaves no final file; omitting it does not cap the download.
A valid cached file is returned immediately unless `force_download=True`. Slashes in a project path
are encoded so the path cannot escape the cache root.

## Another provider

Implement `BaseRegistryProvider` and `BaseFlagProvider`, then register them:

```python
from model_fetcher import register_provider

register_provider("github", GitHubRegistry, GitHubFlags)
```

`ModelFetcher(provider="github")` keeps the same three methods. GitHub itself is not implemented
yet.

## Downstream inference

This package stops at the filesystem. The application that imports it owns the runtime:

```python
from pathlib import Path

from model_fetcher import ModelFetcher


def load_fraud_model() -> Path:
    """Return a local artifact path for the caller's own loader."""
    with ModelFetcher() as fetcher:
        model_path = fetcher.download_from_feature_flag(
            project_id="group/models",
            flag_name="fraud_model",
            context={"environment": "production"},
        )
    # The next line belongs to the inference service, not to model-fetcher:
    # import joblib
    # return joblib.load(model_path)
    return model_path
```

See `examples/downstream_consumer.py`.

## Development

Releases use local Commitizen, matching the pirlruc Python scaffold.

```shell
uv sync --frozen --extra dev
git submodule update --init docs/guardrails .github/scaffold
uv run pre-commit install
sh scripts/check-ci-local.sh
```

`docs/guardrails` is pinned at tag 1.6.0 and `.github/scaffold` at tag 1.5.0. Local and CI gates
read `docs/guardrails/python/profile.thresholds.yml`. CI needs an Actions secret named
`GUARDRAILS_READ_TOKEN` that can read those private repositories.

`uv build` produces the sdist and wheel. An annotated `vX.Y.Z` tag runs the Release workflow, which
publishes a GitHub Release. That release publishes to PyPI with Trusted Publishing.

Decisions are GitHub epics, not ADR markdown files. The backlog lives in `docs/issues.yml`.
Methodology:
[github-issue-adr](https://github.com/pirlruc/methodologies/tree/1.5.0/github-issue-adr).
