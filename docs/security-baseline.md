# Security Baseline — LOCKED

This document freezes the security baseline. It is not a brainstorming
document.

## The handbook's eight items

```text
item                         what the product does                                      where
input validation             contract shapes checked before any Python runs; 400 with   validation/RequestShape,
                             {"error"}; bodies <= 64 KiB with a declared length;        ApiErrorHandler,
                             Idempotency-Key bounded                                     RequestSizeLimitFilter
authentication where         only the operational surface needs it, and it is not       application.properties,
  required                   reachable at all: actuator on internal port 8081          infra/k8s/backend.yaml
authorization                results reachable only by their random UUID; metrics and   (same), cloud-deployment.md
                             health details only in-cluster; IAM/SG scoping in AWS
secret handling              env/Secret/Secrets Manager only; redacted in logs, spans,   logging/SecretRedactor,
                             the database and API responses; secret scan in CI;         ForecastOutcome/AnalysisOutcome
                             full git history scanned clean                              .redacted, scripts/security
safe object/file access      no request value reaches a file path; object keys          storage/ObjectKeys
                             restricted to plain relative keys
rate limiting where exposed  per-client limits on the two routes that start work        security/RateLimitFilter
dependency vulnerability     Trivy over Maven, uv and npm in CI; fails on fixable       scripts/security/scan.sh,
  scanning                   HIGH/CRITICAL; found and fixed 3 CRITICAL Tomcat CVEs      .github/workflows/ci.yml
LLM tool restrictions        eight-tool allowlist, strict schemas, deterministic          planner/validator.py
                             validator; now also bounded plan size, step ids, question
```

Plus transport: HTTPS through an ACM certificate once a domain exists,
HSTS behind it, and `nosniff`/`no-store` on every API response.

## Authentication: where it is required

**Decision (confirmed with the project owner): the product API stays
public; only the operational surface is locked down.** The product has
no user accounts and holds no personal data. A request is a region and
a time. Adding accounts would add an identity provider that is not in
the locked cloud design, for no protected asset. So the question becomes
which surfaces must not be public, and those are made unreachable rather
than password-protected:

```text
port 8080 (Service, NodePort, ALB)     port 8081 (management; no Service, never routed)
  the six API routes                     /actuator/health   full component details
  /readyz  status only                   /actuator/prometheus
  /livez   status only
  /actuator/*  -> 404
```

- `management.server.port=8081`. Kubelet probes and a Prometheus-compatible
  scraper reach it pod-to-pod inside the cluster. The Service exposes only
  8080, and the ALB routes only the API prefixes plus `/readyz`/`/livez`.
- `/readyz` and `/livez` are Boot's health groups served on the main port
  (`add-additional-paths`), with `show-details=never`. They return
  `{"status":"UP"}` and nothing else. `/readyz` includes `db` and `redis`,
  so the frontend's status line and the ALB health check reflect the two
  dependencies every request needs.
- This closes the leak `docs/cloud-deployment.md` flagged:
  `show-details=always` would have shown component details on the public
  ALB. Details now exist only on 8081.
- The frontend's status indicator moved from `/actuator/health` to
  `/readyz`. Compose's healthcheck and the kubelet probes moved to 8081,
  unchanged in meaning.

## Authorization

- A forecast or analysis is fetched by its server-generated UUIDv4
  (122 random bits). Nothing lists them, so knowing an id is the
  capability to read that one result, and ids cannot be guessed. No
  route modifies or deletes a result.
- The AWS side was already least-privilege (`docs/cloud-deployment.md`):
  Pod Identity roles per controller, External Secrets allowed to read
  exactly two secrets, RDS and ElastiCache reachable only from the EKS
  node security group.

## Input validation

The contracts already define request shapes (`docs/forecast-api-contract.md`'s
`RegionSpec`). The backend now enforces them **before** a
Python process or a queued job is spent on a request that can only fail:

```text
region.kind          bbox | coordinates | named
region.value         named: a string of 1-100 chars; bbox: 4 finite numbers; coordinates: 2
cutoff, time_range   ISO 8601 date or date-time, <= 40 chars
question             <= 1,000 chars
intent, operation    <= 64 chars (which values are supported stays the pipeline's call)
Idempotency-Key      1-255 visible ASCII chars (the column is VARCHAR(255): a longer key
                     used to reach the database and come back as a 500)
body                 <= 64 KiB (api.max-request-bytes) -> 413; no Content-Length -> 411
```

A violation is a `400` with the contracts' own `{ "error": "<message>" }`
body. The message names the field and the rule, never echoes the
rejected value, and an unparseable body never returns Jackson's message
(which can quote the body). Semantic failures keep their contract
behavior: a bbox outside California or an unsupported operation is still
a stored FAILED result served as a 422 (`AnalysisControllerTest` pins
this). The `@AssertTrue` checks are `@JsonIgnore`d, so they never become
fields in the JSON sent to Python or stored with a job
(`RequestShapeTest` pins the exact JSON).

## Secret handling

- **Sources.** Real secrets come from the environment: the gitignored
  `.env` for compose, the gitignored `infra/k8s/secret.yaml` for kind,
  and Secrets Manager → External Secrets in AWS. `application.properties`
  holds only the local compose credentials (`ai_earth`/`ai_earth_dev`),
  which every deployment overrides.
- **Redaction before storage (new).** Earlier work redacted Python's error
  text only in logs, but the same text was stored in Postgres and returned
  in the API's 422 body. A FIRMS URL carries the map key in its path, so a
  failed FIRMS call would have handed the key to any API client. The
  outcome is now redacted once, where it comes back from Python
  (`ForecastOutcome.redacted`, `AnalysisOutcome.redacted`). The database,
  the API response, the log line and the span all get the same masked
  text, capped at 2,000 characters. `ForecastWorkerLoggingTest` and
  `AnalysisControllerTest` assert that the stored and returned text no
  longer contains the key.
- **Spans** carry the same redacted text (per the tracing design).
- **Scanning.** The CI job below fails on any committed secret. That it
  really detects one was checked by scanning a throwaway repository with
  a planted AWS key pair: 2 CRITICAL findings, exit 1. The **entire git
  history** was scanned once with gitleaks 8.30.1 (a mirror clone, every
  branch): 97 commits, no leaks.

## Safe object and file access

- **No request value reaches a filesystem path.** The Python entry
  points (`scripts/query/run_*_cli.py`) use fixed constant paths for
  data, history and the model. A `named` region is a dictionary lookup
  (`NAMED_REGIONS[key]`), never a path. History files are chosen by the
  cutoff's integer year and month (`era5_land_%04d_%02d.nc`). The Python
  subprocess is started with a fixed argv and receives the request as JSON
  on stdin. There is no shell, so there is nothing to inject into.
- **Object keys (`ObjectKeys.requireSafe`).** No caller writes through the
  object store yet, so the rule is fixed before one does. Keys must be
  relative `segment/segment/name` paths of `[A-Za-z0-9._-]`, with no
  empty, `.` or `..` segment, no leading or trailing `/`, and at most
  1,024 bytes. An unsafe key is refused before any S3 call
  (`ObjectKeysTest` uses an S3 client that fails if it is ever called).

## Rate limiting

```text
POST /forecasts   10 per minute per client   (RATE_LIMIT_FORECASTS_PER_MINUTE)
POST /analyses    30 per minute per client   (RATE_LIMIT_ANALYSES_PER_MINUTE)
everything else   not limited
over the limit    429, Retry-After = seconds left in the window, {"error"} body
```

- These are the two routes that start real work. A forecast queues a
  Python job that can run for minutes; an analysis holds a request thread
  for a Python subprocess. A person using the UI stays far below the
  limits, which are meant to stop scripts.
- **Shared across replicas:** a fixed one-minute window per route and
  client, counted in the Redis every replica already uses. One Lua script
  does the INCR and the EXPIRE atomically, so a crash between them cannot
  leave a key with no expiry and lock a client out for good.
- **Counted before validation.** A flood of malformed requests is still a
  flood.
- **The client address.** With `server.forward-headers-strategy=native`,
  Tomcat takes `X-Forwarded-For` only when the direct peer is a
  private-network proxy (its default internal-proxy ranges), which is the
  ALB in AWS. A client connecting directly cannot choose its own identity.
- **Fails open.** If Redis is unreachable, the request is allowed and
  `rate_limit_unavailable` is logged. A forecast then fails on the queue
  anyway, and an analysis, which does not need Redis, keeps working.
  The reliability tests exercise "Redis unavailable".

## Dependency vulnerability scanning

`scripts/security/scan.sh`, run locally and by CI's new `security` job,
runs Trivy 0.74.0 (pinned) over what is committed at HEAD. `git archive`
is streamed into the container, so untracked files (`data/`, `.env`,
virtualenvs, build output) are never scanned:

```text
backend/pom.xml              Maven  (transitive deps resolved from the local Maven repository)
ml/uv.lock                   Python
frontend/package-lock.json   npm
every committed file         secrets
```

It fails on a HIGH or CRITICAL vulnerability **that has a fixed
version**, and on any secret. An unfixed CVE is reported but does not
fail the build, since there is nothing to upgrade to. Accepted findings
go in `.trivyignore` with a reason; it is empty.

Two things the first runs taught:

- `pom.xml` has no lockfile, so Trivy resolves transitive dependencies
  from POMs, one request each. Against Maven Central that got this
  machine rate-limited (429, a 30-minute block). The script mounts the
  local Maven repository read-only, which any backend build fills, and
  the CI job runs `./mvnw dependency:resolve` first.
- A bind-mounted full-repo secret scan took over 15 minutes on Windows
  and never finished. Streaming `git archive HEAD` (2.2 MB) takes
  seconds.

**First scan: 3 CRITICAL, all in embedded Tomcat 11.0.24**, which Spring
Boot 4.1.1 (the latest release) manages: CVE-2026-65182,
CVE-2026-65905 and CVE-2026-68525, all fixed in 11.0.25. They are
access-control and authentication bypasses in Tomcat's security
constraints and its DIGEST/FORM authenticators, none of which this
application uses. They are fixable, though, so `pom.xml` overrides
`tomcat.version` to 11.0.26 (the latest patch). The full backend suite
passes on it, and the rescan is clean in all three ecosystems. Drop the
override once a Boot release manages a fixed Tomcat.

## LLM tool restrictions

Already true since the planner was built, and unchanged:

- **Reached over HTTP only through `POST /queries`.** That route is
  rate-limited (20 per minute per IP), caps the question at 1,000
  characters, and runs the planner as a subprocess with a timeout.
- **Retrieved text is data.** Passages returned by `search_docs` come
  only from this repository's `docs/`, are labelled as data in the
  answer prompt, and cannot add a step to the plan: the plan is fixed
  and validated before any passage is retrieved.
- **Allowlisted tools.** Exactly eight tools, each with a strict JSON
  Schema (`additionalProperties: false`, enums for kinds, datasets and
  operations).
- **Structured output only.** The model produces JSON, never runs code,
  and every plan passes the deterministic validator before anything
  executes (`generate_plan` has no path around `validate_plan_or_raise`).
  Regions, time ranges and cutoffs are re-checked by the same functions
  the pipeline uses, and dependencies must point to real earlier steps
  that produce the referenced field.
- **Grounded answers.** The answer generator sees only facts assembled
  from real step results. With no facts, it answers "cannot answer"
  without calling the model.

Added by this task, all enforced in the validator rather than asked for
in the prompt:

```text
at most 8 steps       real plans are small (handbook example DAG: 6 nodes; no benchmark
                      case needs more than 2 matching steps); stops a runaway plan whose
                      every step could start real work
step_id               a letter + up to 31 letters/digits/underscores, via fullmatch --
                      the test caught that `match` with "$" accepted "s1\n"
question <= 1,000     same bound as the API; generate_plan refuses before calling the
                      model, so an oversized question costs nothing
```

The prompt and the model's output schema are deliberately unchanged, so
the planner benchmark stays comparable.

## HTTPS and headers

**Decision (project owner, 2026-09-27): no domain will be bought, so the
product stays internal.** It is reached locally (Docker Compose, the kind
cluster) or, if the AWS stack is ever brought up, over plain HTTP on the
ALB's own AWS DNS name. HTTPS is therefore ready but deliberately not
enabled: the certificate below is never created, and HSTS never fires,
since no request arrives over HTTPS. Enabling it later takes only a
domain, with no code change.

- **Certificate:** `infra/terraform/modules/tls`, an ACM certificate
  validated over DNS. It is created only once `domain_name` is set, and
  it stays unset (above). With `route53_zone_id` set, Terraform creates the
  validation records and waits for issuance; otherwise it outputs the
  records to add by hand. `fmt -check` and `validate` pass in
  `hashicorp/terraform:1.16.4`, the same as the Terraform layout's own
  validation. The Ingress settings that consume it (HTTPS :443,
  `ssl-redirect`, TLS 1.3/1.2 policy) are `docs/cloud-deployment.md`
  gap 9, for later work.
- **`SecurityHeadersFilter`** sets these on every response, refusals
  included:
  - `X-Content-Type-Options: nosniff`: a JSON body is never reinterpreted
    as HTML.
  - `Cache-Control: no-store`: statuses change, and results are fetched
    by id.
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains`:
    only when the request arrived over HTTPS (the ALB's
    `X-Forwarded-Proto`). It is never sent over plain HTTP.

## Filter order

```text
RequestIdFilter          HIGHEST       request_id, http_request log line
SecurityHeadersFilter    HIGHEST + 1   headers on every response
RequestSizeLimitFilter   HIGHEST + 2   411/413 before anything reads the body
RateLimitFilter          HIGHEST + 3   429 before any work
```

## Tests

```text
OpsSurfaceIntegrationTest            3  public port: /actuator/* all 404; /livez,/readyz UP with
                                        no details; management port: full health + metrics
RequestShapeTest                     4  region/timestamp rules; field names in violations;
                                        checks never serialized
RequestValidationIntegrationTest     6  valid still 201; bad kind/bbox/cutoff 400 naming the field,
                                        value not echoed; bad JSON 400 without quoting; long
                                        question 400; 256-char Idempotency-Key 400 (was 500);
                                        413 oversized, 411 chunked
RateLimitFilterTest                  4  key per route+client; 429 + Retry-After, request never runs;
                                        fails open; reads never counted
RateLimitIntegrationTest             1  real Redis: 3/min then 429; separate budget per route;
                                        reads and probes unlimited
ObjectKeysTest                       3  plain keys pass; traversal/absolute/odd refused; refused
                                        before any S3 call
SecurityHeadersIntegrationTest       2  headers on success and refusal; HSTS only via HTTPS proxy
AnalysisControllerTest              +1  stored and returned error redacted
ForecastWorkerLoggingTest           +1  stored forecast error redacted
planner (pytest)                    +5  8-step limit; runaway plan refused; step_id rule
                                        (8 cases); long question refused; no model call for it
PrometheusEndpointIntegrationTest    ~  now scrapes the management port
StructuredLoggingIntegrationTest     ~  now requests /readyz
```

Backend suite: **146 tests, 0 failures** (121 before this task).
Planner suite: 78 passed. Each rate-limited test context counts under
its own Redis keys (`src/test/resources/config/application.properties`),
so test classes cannot use up each other's budget.

## Verified on the local kind cluster

The backend image was rebuilt, imported into the kind node and rolled
out with the updated `infra/k8s/backend.yaml`. The new pod became Ready
through the kubelet probes on the management port (`port: management`),
and the old pod was replaced. From the host, through the NodePort:

```text
GET /readyz                200  {"status":"UP"}
GET /livez                 200  {"status":"UP"}
GET /actuator/health       404
GET /actuator/prometheus   404
response headers           X-Content-Type-Options: nosniff, Cache-Control: no-store
Service ports              8080 only
```

From inside the pod, on the management port:

```text
GET :8081/actuator/prometheus  200
GET :8081/actuator/health      {"components":{"db":{"details":{"database":"PostgreSQL",...
```

## Found, not fixed here

- **Python CI is already red.** `ruff check .` reports 20 findings and
  `mypy src` reports 2 errors, all in files from earlier commits
  (`data/history.py`, `forecast/build_dataset.py` and others), none in
  code this task touched. It is a separate cleanup.
- **The backend image cannot be built without the trained model.**
  `backend/Dockerfile` copies `ml/artifacts/production_model_v1` (since
  the production-model commit), and that directory exists only after
  `scripts/models/train_production_model.py` has run. On this machine it
  has not, so the image for the kind check above was built with an empty
  placeholder directory, removed right after the build. That is enough
  to verify ports and probes, but a forecast in that image fails.
