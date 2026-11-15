# Object Storage Contract

This document defines the object storage abstraction.

Infrastructure: `infra/docker/docker-compose.yml` runs `bitnamilegacy/minio`
(MinIO no longer publishes community images) on port `9000`
(S3 API) / `9001` (web console), credentials `ai_earth`/`ai_earth_dev`.
These match the Postgres credentials for consistency; the services are
not the same. Run `docker compose up -d` from `infra/docker/` before
using it, same as Postgres.

## The abstraction

```java
public interface ObjectStore {
    void put(String key, byte[] content, String contentType);
    Optional<byte[]> get(String key);
    boolean exists(String key);
    void delete(String key);
}
```

Exactly the four required operations. `get` returns
`Optional.empty()` for a missing key rather than throwing, matching how
`AnalysisStore`/`ForecastStore` already return `Optional` for a missing
id.

## Why MinIO, and why the S3 SDK

MinIO is S3-API-compatible, so `S3ObjectStore` is written against the
AWS SDK v2 `S3Client` (`software.amazon.awssdk:s3`), pointed at
MinIO's endpoint with path-style access
(`S3ClientConfig`/`object-store.endpoint`). The same code works
unchanged against AWS S3 (see `docs/cloud-deployment.md` and
`docs/s3-artifacts.md`) by changing only the
`object-store.*` properties, with no code change and no second
implementation to maintain.

The target bucket (`object-store.bucket`, default `ai-earth-artifacts`)
is created automatically on startup if it doesn't exist yet
(`S3ObjectStore`'s constructor), the same zero-manual-setup posture as
Flyway auto-applying the Postgres schema.

## Out of scope

No Java caller writes through this abstraction yet. `AnalysisStore` and
`ForecastStore` still store their (currently modest-sized) results
directly as Postgres `jsonb`, per `docs/persistence-schema.md`. The
first caller will be something that needs to store a large object (a
forecast grid for all of California, a model artifact or a plot)
outside a table row. This document fixes only the interface and the
infrastructure, not which caller uses it first or how keys are named. `S3ObjectStoreTest` checks
put, get, exists and delete against the local MinIO, in the same way
that `BackendApplicationTests` checks the Postgres connection.
