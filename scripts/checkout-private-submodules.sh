#!/bin/sh
# Fetch the pinned private submodules at their gitlink SHAs (CI-021, CI-025).
# The token is used only on the fetch URL and is not stored as a remote.
set -eu

token="${GUARDRAILS_READ_TOKEN:-}"
if [ -z "${token}" ]; then
  echo "error: GUARDRAILS_READ_TOKEN is required to fetch private submodules" >&2
  exit 1
fi

export GIT_TERMINAL_PROMPT=0
root="$(git rev-parse --show-toplevel)"
cd "${root}"

checkout_one() {
  path="$1"
  repo="$2"
  sha="$(git rev-parse "HEAD:${path}")"
  test -n "${sha}"
  rm -rf "${path}"
  mkdir -p "${path}"
  git -C "${path}" init --quiet
  git config --global --add safe.directory "${root}/${path}"
  git -C "${path}" fetch --depth 1 \
    "https://x-access-token:${token}@github.com/${repo}.git" \
    "${sha}"
  git -C "${path}" checkout --detach FETCH_HEAD
  git -C "${path}" remote add origin "https://github.com/${repo}.git"
}

checkout_one docs/guardrails pirlruc/guardrails
checkout_one .github/scaffold pirlruc/github-scaffold
test -f docs/guardrails/python/profile.thresholds.yml
echo "Checked out docs/guardrails and .github/scaffold at their gitlinks."
