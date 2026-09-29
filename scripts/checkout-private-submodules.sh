#!/bin/sh
# Fetch the pinned docs/guardrails gitlink (CI-021, CI-025).
# The token is sent as an Authorization header and is not stored as a remote.
#
# .github/scaffold stays a gitlink for local template sync. Neither
# GUARDRAILS_READ_TOKEN nor COMMONDEVOPS_READ_TOKEN can read
# pirlruc/github-scaffold, so CI uses the vendored link linter under scripts/.
set -eu

token="${GUARDRAILS_READ_TOKEN:-}"
if [ -z "${token}" ]; then
  echo "error: GUARDRAILS_READ_TOKEN is required to fetch docs/guardrails" >&2
  exit 1
fi

export GIT_TERMINAL_PROMPT=0
root="$(git rev-parse --show-toplevel)"
cd "${root}"

path="docs/guardrails"
repo="pirlruc/guardrails"
sha="$(git rev-parse "HEAD:${path}")"
test -n "${sha}"
rm -rf "${path}"
mkdir -p "${path}"
git -C "${path}" init --quiet
git -C "${path}" config safe.directory "${root}/${path}"
# The token stays in the git process environment, not the remote URL or argv.
auth="$(printf 'x-access-token:%s' "${token}" | base64 | tr -d '\n')"
GIT_CONFIG_COUNT=1 \
  GIT_CONFIG_KEY_0=http.extraheader \
  GIT_CONFIG_VALUE_0="AUTHORIZATION: basic ${auth}" \
  git -C "${path}" fetch --depth 1 "https://github.com/${repo}.git" "${sha}"
git -C "${path}" checkout --detach FETCH_HEAD
git -C "${path}" remote add origin "https://github.com/${repo}.git"
test -f docs/guardrails/python/profile.thresholds.yml
echo "Checked out docs/guardrails at its gitlink."
