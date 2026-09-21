# Improvements

## Tracking

### High Priority

- [x] **Pin `docs/guardrails` at tag 1.6.0 and `.github/scaffold` at tag 1.5.0.** CI fetches those
  private gitlinks with the Actions secret `GUARDRAILS_READ_TOKEN`.
- [ ] **Store `GUARDRAILS_READ_TOKEN` as an Actions secret** with contents read on
  `pirlruc/guardrails` and `pirlruc/github-scaffold`. Quality, test, and docs workflows fail closed
  without it.
- [ ] **Open the Phase 1 epics in GitHub from `docs/issues.yml`.** The agent GitHub CLI is read-only
  here, so the decision records exist in-repo and still need live epic/task issues.

### Medium Priority

- [ ] **Add a GitHub Releases provider** behind `register_provider("github", ...)` without changing
  `ModelFetcher`.
- [x] **Coverage gate.** Statement and branch coverage both use the 95 percent floors in guardrails
  1.6.0 (`scripts/check-python-coverage.py`).
- [ ] **Dependabot access to the private submodules.** `gitsubmodule` is in the monthly group. Add a
  Dependabot git registry only after `DEPENDABOT_GITHUB_TOKEN` exists.
- [ ] **Configure PyPI Trusted Publishing** for `model-fetcher` and
  `.github/workflows/publish-pypi.yml` before the first publish.

### Low Priority

- [ ] **Retry transient GitLab 5xx responses.** Downloads fail once today.
- [ ] **Cross-process cache locking.** The `<file>.downloading` name follows the spec and is not
  unique per writer.
- [ ] **Review the Node 24 force flag** after every action, including `gitleaks-action`, declares
  Node 24 natively.
