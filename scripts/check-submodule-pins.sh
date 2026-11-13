#!/bin/sh
# SC-DEP-004: gitlink SHA must equal the peeled annotated tag named here.
# common-pins-verify runs this file with sh, so it stays POSIX.
set -eu

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

# Peeled commits for annotated tags guardrails 1.15.0 and github-scaffold 1.12.0.
GR_TAG="1.15.0"
GR_EXPECT="2d4bb70e95449f6922781716857adeb22badf676"
SC_TAG="1.12.0"
SC_EXPECT="9c443ea978851768f451b1df2020dd86dfb1a967"

gr="$(git rev-parse 'HEAD:docs/guardrails')"
sc="$(git rev-parse 'HEAD:.github/scaffold')"

status=0
if [ "${gr}" != "${GR_EXPECT}" ]; then
  echo "SC-DEP-004: docs/guardrails gitlink ${gr} != ${GR_TAG} ${GR_EXPECT}" >&2
  status=1
fi
if [ "${sc}" != "${SC_EXPECT}" ]; then
  echo "SC-DEP-004: .github/scaffold gitlink ${sc} != ${SC_TAG} ${SC_EXPECT}" >&2
  status=1
fi
if [ "${status}" -ne 0 ]; then
  exit 1
fi

echo "SC-DEP-004: docs/guardrails @ ${GR_TAG} (${GR_EXPECT})"
echo "SC-DEP-004: .github/scaffold @ ${SC_TAG} (${SC_EXPECT})"
