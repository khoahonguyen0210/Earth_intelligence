# Object Storage Contract — LOCKED

This document freezes the object storage abstraction. It is not a
brainstorming document.

Infrastructure: `infra/docker/docker-compose.yml` runs `bitnamilegacy/minio`
(MinIO no longer publishes community images) on port `9000`
(S3 API) / `9001` (web console), credentials `ai_earth`/`ai_earth_dev` —
matching Postgres's credentials for consistency, not because they're the
same service. Run `docker compose up -d` from `infra/docker/` before
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
real AWS SDK v2 `S3Client` (`software.amazon.awssdk:s3`), pointed at
MinIO's endpoint with path-style access
(`S3ClientConfig`/`object-store.endpoint`). The same code will work
unchanged against real AWS S3 in the later infrastructure phase
(the "AWS + Terraform" plan) by only changing
`object-store.*` properties — no code change, no second implementation
to maintain.

The target bucket (`object-store.bucket`, default `ai-earth-artifacts`)
is created automatically on startup if it doesn't exist yet
(`S3ObjectStore`'s constructor), the same zero-manual-setup posture as
Flyway auto-applying the Postgres schema.

## What this document does not define

No Java caller writes through this abstraction yet — `AnalysisStore`/
`ForecastStore` still store their (currently modest-sized) results
directly as Postgres `jsonb`, per `docs/persistence-schema.md`. The
natural first real caller is a future task that needs to store something
genuinely large — a full-California forecast grid, a model artifact, a
plot — outside a relational row; this document only fixes the interface
and the infrastructure that task builds against, not which caller uses
it first or what key-naming scheme it uses. `S3ObjectStoreTest` proves
the actual put/get/exists/delete wiring against the real local MinIO,
the same way `BackendApplicationTests` proves the real Postgres wiring.
