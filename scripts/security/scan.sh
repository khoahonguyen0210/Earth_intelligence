#!/usr/bin/env sh
# Task 13.4: dependency vulnerability and secret scan of the repository
# (docs/security-baseline.md). One tool, Trivy, covers every ecosystem the
# project ships -- backend/pom.xml (Maven), ml/uv.lock (Python) and
# frontend/package-lock.json (npm) -- plus committed secrets.
#
# Scans exactly what is committed at HEAD: `git archive` is streamed into
# the Trivy container, so untracked local files (data/, .env, virtualenvs,
# build output) are never scanned or reported, and nothing is bind-mounted
# (a Windows bind mount made a full-repo secret scan take over 15 minutes).
# Commit first to scan a change.
#
# Fails (exit 1) on a HIGH or CRITICAL vulnerability that has a fixed
# version, or on any secret. A vulnerability with no fix yet is reported
# but does not fail the build: there is nothing to upgrade to. An
# accepted finding goes in .trivyignore with the reason next to it.
#
# backend/pom.xml has no lockfile, so Trivy resolves its transitive
# dependencies from POMs. Those come from the local Maven repository
# (mounted read-only), which any backend build fills -- one request per
# POM against Maven Central instead gets the IP rate-limited (429, a
# 30-minute block, as the first run here found). Run a backend build, or
# `./mvnw dependency:resolve` in backend/, before the scan.
#
# Requires git and Docker. Run from the repository root, locally or in
# CI:
#
#   sh scripts/security/scan.sh
set -eu

TRIVY_IMAGE="aquasec/trivy:0.74.0"
MAVEN_REPO="${MAVEN_REPO:-$HOME/.m2/repository}"

# Git Bash on Windows would otherwise rewrite the container-side path.
export MSYS_NO_PATHCONV=1

git archive --format=tar HEAD | docker run --rm -i \
  -v trivy-cache:/root/.cache/trivy \
  -v "$MAVEN_REPO:/root/.m2/repository:ro" \
  --entrypoint sh \
  "$TRIVY_IMAGE" -c '
    mkdir -p /src && tar -x -C /src &&
    trivy fs \
      --scanners vuln,secret \
      --severity HIGH,CRITICAL \
      --ignore-unfixed \
      --exit-code 1 \
      --ignorefile /src/.trivyignore \
      /src'
