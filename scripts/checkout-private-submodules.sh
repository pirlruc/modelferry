#!/bin/sh
# Fetch the pinned private submodules at their gitlink SHAs (CI-021, CI-025).
# Each token is sent as an Authorization header and is not stored as a remote.
#
# GUARDRAILS_READ_TOKEN reads pirlruc/guardrails.
# github-scaffold is a different private repository. Prefer SCAFFOLD_READ_TOKEN,
# then COMMONDEVOPS_READ_TOKEN, then GUARDRAILS_READ_TOKEN.
set -eu

guardrails_token="${GUARDRAILS_READ_TOKEN:-}"
if [ -z "${guardrails_token}" ]; then
  echo "error: GUARDRAILS_READ_TOKEN is required to fetch docs/guardrails" >&2
  exit 1
fi

scaffold_token="${SCAFFOLD_READ_TOKEN:-${COMMONDEVOPS_READ_TOKEN:-${guardrails_token}}}"
if [ -n "${SCAFFOLD_READ_TOKEN:-}" ]; then
  scaffold_source="SCAFFOLD_READ_TOKEN"
elif [ -n "${COMMONDEVOPS_READ_TOKEN:-}" ]; then
  scaffold_source="COMMONDEVOPS_READ_TOKEN"
else
  scaffold_source="GUARDRAILS_READ_TOKEN"
fi

export GIT_TERMINAL_PROMPT=0
root="$(git rev-parse --show-toplevel)"
cd "${root}"

checkout_one() {
  path="$1"
  repo="$2"
  repo_token="$3"
  sha="$(git rev-parse "HEAD:${path}")"
  test -n "${sha}"
  rm -rf "${path}"
  mkdir -p "${path}"
  git -C "${path}" init --quiet
  git -C "${path}" config safe.directory "${root}/${path}"
  # The token stays in the git process environment, not the remote URL or argv.
  auth="$(printf 'x-access-token:%s' "${repo_token}" | base64 | tr -d '\n')"
  GIT_CONFIG_COUNT=1 \
    GIT_CONFIG_KEY_0=http.extraheader \
    GIT_CONFIG_VALUE_0="AUTHORIZATION: basic ${auth}" \
    git -C "${path}" fetch --depth 1 "https://github.com/${repo}.git" "${sha}"
  git -C "${path}" checkout --detach FETCH_HEAD
  git -C "${path}" remote add origin "https://github.com/${repo}.git"
}

echo "Fetching docs/guardrails with GUARDRAILS_READ_TOKEN."
checkout_one docs/guardrails pirlruc/guardrails "${guardrails_token}"
echo "Fetching .github/scaffold with ${scaffold_source}."
checkout_one .github/scaffold pirlruc/github-scaffold "${scaffold_token}"
test -f docs/guardrails/python/profile.thresholds.yml
test -f .github/scaffold/scripts/lint-doc-links.py
echo "Checked out docs/guardrails and .github/scaffold at their gitlinks."
