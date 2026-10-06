#!/usr/bin/env sh
set -eu

TRIVY_IMAGE="aquasec/trivy:0.74.0"
MAVEN_REPO="${MAVEN_REPO:-$HOME/.m2/repository}"

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
