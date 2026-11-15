# Docker Images

This document describes the service images. `docs/docker-compose-stack.md`
connects them into one stack.

## Two images, not three

```text
backend/Dockerfile   Spring Boot (JRE 21) + Python (managed by uv) + ml/
frontend/Dockerfile  React/Vite static build, served by nginx
```

The plan listed three images: backend, python-worker and frontend.
There is no separate python-worker image, because the project uses only
the services the application needs. Java reaches Python through
`PythonForecastRunner` and `PythonAnalysisRunner`, which use
`ProcessBuilder` to run `python scripts/query/run_forecast_cli.py` as a
subprocess on the same machine. They talk over the child process's
stdin and stdout, not over the network. So there is no separate
python-worker process that could have its own image. The Python
environment is a local dependency of the backend process, in the same
way as a JDBC driver. That is why one backend image holds both
runtimes. Splitting them into two containers would mean turning the
bridge into a network call, which is a design change, not packaging.

`ForecastWorker`, the actual worker (a Java `@Scheduled` component that
polls Redis), already runs inside the same Spring Boot process as the
rest of the backend. It was never a separate deployable unit.

## backend/Dockerfile

```text
stage 1 (maven:3.9-eclipse-temurin-21): mvn package -> the Spring Boot jar
stage 2 (eclipse-temurin:21-jre-jammy): jar + uv-managed Python venv
  (ml/pyproject.toml + ml/uv.lock, `uv sync --frozen`) + scripts/ +
  data/raw/ (the same small sample files that the scripts under
  scripts/query/ read locally)
```

`uv` manages the interpreter, instead of a Python package from `apt`, so
the image's Python version follows the `requires-python` setting in
`ml/pyproject.toml`, not whatever version the base image provides.
`FORECAST_PYTHON_EXECUTABLE`, `ANALYSIS_PYTHON_EXECUTABLE` and
`*_PYTHON_WORKDIR` (existing placeholders in `application.properties`
that can be overridden) point at the image's venv and its `/app` working
directory. No Java code had to change to run the bridge in a container.

## frontend/Dockerfile

```text
stage 1 (node:22-alpine): npm ci && npm run build -> dist/
stage 2 (nginx:1.27-alpine): serves dist/ as static files
```

`API_BASE_URL` in `src/api/client.ts` (`http://localhost:8080`) is
unchanged. The browser makes the request, not the frontend container,
and the browser runs on the host. `docker-compose.yml` maps the backend
container's port 8080 to the host for this reason, so a local Compose
stack needs no reverse proxy and no URL replacement at build time.

## Out of scope

Connecting the two images with the postgres, redis and minio services,
and the environment variables that link them, is described in
`docs/docker-compose-stack.md`. `docs/clean-start-test.md` checks that
the whole stack works end to end.
