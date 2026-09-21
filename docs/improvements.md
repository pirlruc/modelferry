# Improvements

## Tracking

### High Priority

- [ ] **Pin `docs/guardrails` when the private repository is readable.** This environment received
  HTTP 404 for `pirlruc/guardrails`, `pirlruc/github-scaffold`, and `pirlruc/methodologies`. Quality
  gates were copied from the public `pirlruc/pymjolnir` Python scaffold instead of a submodule pin.
- [ ] **Open the Phase 1 epics in GitHub from `docs/issues.yml`.** The agent GitHub CLI is read-only
  here, so the decision records exist in-repo and still need live epic/task issues.

### Medium Priority

- [ ] **Add a GitHub Releases provider** behind `register_provider("github", ...)` without changing
  `ModelFetcher`.
- [ ] **Publish a coverage gate** once a threshold is chosen. Tests cover the cache, both GitLab
  registries, flag payloads, and the facade. CI runs pytest without a coverage floor.
- [ ] **Configure PyPI Trusted Publishing** for `model-fetcher` and
  `.github/workflows/publish-pypi.yml` before the first publish.

### Low Priority

- [ ] **Retry transient GitLab 5xx responses.** Downloads fail once today.
- [ ] **Cross-process cache locking.** The `<file>.downloading` name follows the spec and is not
  unique per writer.
- [ ] **Review the Node 24 force flag** after every action, including `gitleaks-action`, declares
  Node 24 natively.
