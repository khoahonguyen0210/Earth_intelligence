# Forecast Jobs in DynamoDB

Forecast job status and metadata can be kept in Amazon DynamoDB instead
of Postgres. The backend picks the store at startup:

```bash
FORECAST_STORE=postgres   # default
FORECAST_STORE=dynamodb
```

Both stores implement `ForecastStore`
(`backend/src/main/java/com/example/backend/forecast/`), and both pass
the same contract tests (`ForecastStoreContract`): lookups by job ID and
by idempotency key, claiming a job exactly once, and the recovery
queries that find abandoned or stuck jobs. The API, worker and recovery
code are unchanged.

## Table layout

One table, `ai-earth-forecast-jobs` by default, with partition key `pk`:

| Item | `pk` | Attributes |
|---|---|---|
| Job | `JOB#<job id>` | `id`, `status`, `request`, `result` or `result_key`, `error`, `attempts`, `created_at`, `updated_at` (epoch ms), `idempotency_key`, `trace_parent` |
| Idempotency key | `IDEMPOTENCY#<key>` | `job_id` |

| Access | How |
|---|---|
| Job by ID | `GetItem` on `JOB#<id>`, strongly consistent |
| Job by idempotency key | `GetItem` on `IDEMPOTENCY#<key>`, then the job |
| Claim a waiting job | `UpdateItem` with condition `status IN (PENDING, RETRYING)` |
| Stuck or abandoned jobs | `Query` on the `status-updated_at` index: `status = :s AND updated_at < :before` |

- **Idempotency.** A job with a key is written in one transaction with
  its `IDEMPOTENCY#` item, conditional on the key being unused or already
  owned by that job. A second job with the same key fails the condition,
  and the API returns the first job, as it does with Postgres.
- **Concurrency.** Claiming, ending an abandoned attempt and refreshing a
  waiting job are conditional updates, so two workers cannot both claim
  a job, and recovery cannot overwrite a job that just moved on.
- **Large results.** A result up to 256 KB is stored in the item. A
  larger one goes to the object store (MinIO or S3) at
  `forecasts/<job id>/result.json`, and the item keeps `result_key`,
  since a DynamoDB item is limited to 400 KB.
- **Errors.** AWS SDK failures surface as Spring `DataAccessException`,
  so the worker backs off and retries exactly as it does when Postgres
  is down.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `FORECAST_STORE` | `postgres` | `dynamodb` to use this store |
| `FORECAST_JOBS_TABLE` | `ai-earth-forecast-jobs` | Table name |
| `AWS_REGION` | `us-west-2` | Region |
| `DYNAMODB_ENDPOINT` | empty | Set only for DynamoDB Local |
| `DYNAMODB_ACCESS_KEY`, `DYNAMODB_SECRET_KEY` | empty | Static keys; empty uses the default AWS chain (pod identity on EKS) |
| `DYNAMODB_CREATE_TABLE` | `false` | Create the table at startup (local use) |
| `DYNAMODB_INLINE_RESULT_MAX_BYTES` | `262144` | Largest result kept in the item |

## Running locally

`infra/docker` runs DynamoDB Local next to the other services, in memory.
If port 8000 is taken, set `DYNAMODB_PORT`.

```bash
cd infra/docker
FORECAST_STORE=dynamodb docker compose up -d --build
```

## On AWS

`infra/terraform/modules/jobs` creates the table with on-demand billing,
the `status-updated_at` index, point-in-time recovery, encryption at
rest and deletion protection. The backend's pod identity may get, put,
update and query the table and its index, and nothing else. The table
name is the `forecast_job_table` output.

## Tests

`DynamoDbForecastStoreIntegrationTest` runs the contract and the
large-result cases against DynamoDB Local (`DYNAMODB_ENDPOINT`, default
`http://localhost:8000`). `DynamoDbForecastStoreTest` covers error
translation with a mocked client, and `DynamoDbStoreWiringTest` starts
the whole application with `FORECAST_STORE=dynamodb`.
