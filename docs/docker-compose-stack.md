# Docker Compose Stack — LOCKED

This document freezes the local Docker Compose stack per Task 10.2 of
the Execution Handbook. It is not a brainstorming document. It wires
`docs/docker-images.md` (Task 10.1)'s two built images together with
the infrastructure services Phase 6 already locked (Postgres/PostGIS,
Redis, MinIO); `docs/clean-start-test.md` (Task 10.3) verifies the
result actually works.

## The stack

```text
infra/docker/docker-compose.yml
```

```text
postgres  -- postgis/postgis:16-3.5, already existed (Task 6.3)
redis     -- redis:7-alpine, already existed (Task 6.5)
minio     -- quay.io/minio/minio, already existed (Task 6.4)
backend   -- built from backend/Dockerfile (Task 10.1) -- Spring Boot +
             Python/ml, port 8080
frontend  -- built from frontend/Dockerfile (Task 10.1) -- nginx serving
             the Vite build, port 5173 -> container port 80
```

Only these five: the handbook's own Task 10.2 instruction ("use only
the services the application actually needs") is why there is no
separate worker service (`docs/docker-images.md` already explains why)
and no reverse proxy (the frontend's `API_BASE_URL` is the browser's own
`http://localhost:8080`, reached directly since the backend's port is
published straight to the host).

`backend` declares `depends_on` with `condition: service_healthy` on
all three infrastructure services, so it never starts racing against a
Postgres/Redis/MinIO that is still booting -- Flyway migrations, the
JPA `ddl-auto: validate` check, and the Redis/MinIO client
initialization all assume a live, ready dependency.

## Environment wiring

```text
SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/ai_earth
REDIS_HOST=redis
OBJECT_STORE_ENDPOINT=http://minio:9000
```

No Java code changed for this: `spring.datasource.url` is overridden
via Spring Boot's standard relaxed environment-variable binding
(`SPRING_DATASOURCE_URL` -> `spring.datasource.url`), and
`REDIS_HOST`/`OBJECT_STORE_ENDPOINT` were already-overridable
`application.properties` placeholders (Tasks 6.4/6.5), previously only
ever pointed at `localhost`/`127.0.0.1` for a locally-run backend.
Compose's own internal DNS (service name -> container) is what makes
`postgres`/`redis`/`minio` resolve at all here.

```text
env_file: ../../.env
```

The backend service also loads the repository's real, gitignored local
`.env` -- the same file every `scripts/*.py` real-caller already reads
via `python-dotenv`. This is Task 10.3's own fix, not this task's: see
`docs/clean-start-test.md` for why the Python subprocess bridge needs
`FIRMS_MAP_KEY` from it.

## What this document does not define

Actually bringing the stack up from nothing and verifying health,
Earth analysis, and forecast requests all really work is Task 10.3's
job, not this one's -- this task only fixes what the stack contains and
how its pieces are wired.
