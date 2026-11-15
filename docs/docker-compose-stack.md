# Docker Compose Stack

The local Docker Compose stack runs the two images from
`docs/docker-images.md` together with Postgres/PostGIS, Redis and
MinIO. `docs/clean-start-test.md` checks that the stack works.

## Services

```text
infra/docker/docker-compose.yml
```

```text
postgres  postgis/postgis:16-3.5
redis     redis:7-alpine
minio     bitnamilegacy/minio
backend   built from backend/Dockerfile: Spring Boot + Python/ml,
          port 8080
frontend  built from frontend/Dockerfile: nginx serving the Vite
          build, port 5173 -> container port 80
```

The stack has only these five services, because it uses only what the
application needs. There is no separate worker service (see
`docs/docker-images.md`) and no reverse proxy. The frontend's
`API_BASE_URL` is `http://localhost:8080`, which the browser reaches
directly because the backend's port is published to the host.

`backend` uses `depends_on` with `condition: service_healthy` on all
three infrastructure services, so it never starts before Postgres,
Redis or MinIO is ready. Flyway migrations, the JPA
`ddl-auto: validate` check and the Redis and MinIO clients all expect a
running dependency.

## Environment

```text
SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/ai_earth
REDIS_HOST=redis
OBJECT_STORE_ENDPOINT=http://minio:9000
```

No Java code changed. Spring Boot's standard relaxed binding maps
`SPRING_DATASOURCE_URL` to `spring.datasource.url`, and `REDIS_HOST` and
`OBJECT_STORE_ENDPOINT` were already placeholders in
`application.properties` that could be overridden; before, they only
pointed at `localhost` or `127.0.0.1` for a backend run on the host.
Compose's internal DNS (service name to container) makes `postgres`,
`redis` and `minio` resolve.

```text
env_file: ../../.env
```

The backend service also loads the repository's local `.env`, which
git ignores. The scripts under `scripts/` read the same file through
`python-dotenv`. This line was added by the clean-start test; see
`docs/clean-start-test.md` for why the Python subprocess needs
`FIRMS_MAP_KEY` from it.

## Out of scope

Starting the stack from nothing and checking health, Earth analysis and
forecast requests is done in `docs/clean-start-test.md`. This document
only describes what the stack contains and how its parts connect.
