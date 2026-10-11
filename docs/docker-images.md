# Docker Images — LOCKED

This document freezes the service Docker images. It is not a
brainstorming document. `docs/docker-compose-stack.md` wires
these images together; this task only builds them.

## Two images, not three

```text
backend/Dockerfile   -- Spring Boot (JRE 21) + Python (uv-managed) + ml/
frontend/Dockerfile  -- React/Vite static build, served by nginx
```

The plan lists three: backend, python-worker, frontend. There is no
separate python-worker image here, and this is a deliberate reading of
the project's own "use only the services the application actually needs,"
not a shortcut: earlier work already locked how Java reaches Python --
`PythonForecastRunner`/`PythonAnalysisRunner` construct a `ProcessBuilder`
and run `python scripts/query/run_forecast_cli.py` as a same-machine
subprocess, communicating over the child process's stdin/stdout, not a
network call. There is no independent, addressable "python-worker"
process in the real architecture to give its own image -- the Python
environment is a same-machine dependency of the backend process, the
same way a JDBC driver is. `backend/Dockerfile`'s single image bundles
both runtimes for exactly this reason: splitting them into two
containers would require redesigning that bridge into a real network
call, which is an already-locked decision to reopen, not
something packaging what already exists is scoped to do.

`ForecastWorker` -- the actual "worker" role, a Java
`@Scheduled` component polling Redis -- already runs inside the same
Spring Boot process as the rest of the backend; it was never a separate
deployable unit either.

## backend/Dockerfile

```text
stage 1 (maven:3.9-eclipse-temurin-21): mvn package -> the Spring Boot jar
stage 2 (eclipse-temurin:21-jre-jammy): jar + uv-managed Python venv
  (ml/pyproject.toml + ml/uv.lock, `uv sync --frozen`) + scripts/ +
  data/raw/ (the same small real sample files every scripts/query/*.py
  real-caller already reads locally)
```

`uv` (not a system `apt` Python package) manages the interpreter itself,
so the image's Python version tracks `ml/pyproject.toml`'s own
`requires-python` constraint directly rather than whatever version the
base image's package manager happens to carry.
`FORECAST_PYTHON_EXECUTABLE`/`ANALYSIS_PYTHON_EXECUTABLE`/
`*_PYTHON_WORKDIR` (already-overridable `application.properties`
placeholders) point at this image's own venv and `/app`
working directory -- no Java source change was needed to containerize
the existing bridge.

## frontend/Dockerfile

```text
stage 1 (node:22-alpine): npm ci && npm run build -> dist/
stage 2 (nginx:1.27-alpine): serves dist/ as static files
```

`src/api/client.ts`'s `API_BASE_URL` (`http://localhost:8080`) is
unchanged: the browser, not the frontend container, makes that request,
and it runs on the host -- `docker-compose.yml` maps the backend
container's port 8080 straight through to the host for exactly this
reason, so no reverse proxy or build-time URL substitution is needed for
a local compose stack.

## What this document does not define

Wiring these two images together with the existing postgres/redis/minio
services, and the environment variables that connect them, is the
Docker Compose stack's job. Verifying the whole stack actually works end to end (health
checks, a real Earth analysis, a real forecast) is the clean-start test's.
