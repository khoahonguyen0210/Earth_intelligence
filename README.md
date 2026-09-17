<div align="center">

# AI Earth Intelligence & Forecasting Engine

AI Earth Intelligence & Forecasting Engine is a web application that answers natural-language questions about Earth, such as wildfire counts and trends or a 24-hour wildfire-risk forecast. Every answer is backed by real ingested Earth data and a trained model, and the evidence behind each number is attached to it.

![Java](https://img.shields.io/badge/Java-ED8B00?logo=openjdk&logoColor=white)
![Spring Boot](https://img.shields.io/badge/Spring_Boot-6DB33F?logo=springboot&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-20232A?logo=react&logoColor=61DAFB)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![Kubernetes](https://img.shields.io/badge/Kubernetes-326CE5?logo=kubernetes&logoColor=white)
![Terraform](https://img.shields.io/badge/Terraform-844FBA?logo=terraform&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-232F3E?logo=amazonaws&logoColor=white)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

![AI Earth Intelligence Preview](docs/images/home.png)

</div>

```text
"How many wildfires occurred in the Bay Area during August 2024?"
"What's the wildfire risk for California starting tomorrow?"
```

## Table of Contents

- [Features](#features)
- [Technology Stack](#technology-stack)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start with Docker](#quick-start-with-docker)
- [Local Development](#local-development)
- [Environment Variables](#environment-variables)
- [REST API](#rest-api)
- [Project Structure](#project-structure)
- [Deployment](#deployment)
- [Results](#results)
- [Testing](#testing)
- [Security Notes](#security-notes)
- [Docs](#docs)
- [Contributing](#contributing)
- [License](#license)

## Features

- Ask questions in plain English. An LLM turns the question into a plan, and a deterministic validator checks that plan before anything runs, so the LLM never executes arbitrary logic.
- Query real Earth data: NASA FIRMS fire history, Copernicus ERA5-Land weather, Copernicus DEM elevation and slope, and ESA WorldCover land cover.
- Request a 24-hour wildfire-risk forecast from a calibrated XGBoost model that scores a fixed California grid.
- Track each forecast as an async job with a real queued, running, completed, or failed status.
- See the evidence for every answer, including the dataset, time range, region, model version, and calibration.
- View results on an interactive map and browse the measured benchmark results in the app.

## Technology Stack

<div align="center">

**Languages**

![Java](https://img.shields.io/badge/Java-ED8B00?logo=openjdk&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?logo=javascript&logoColor=black)
![SQL](https://img.shields.io/badge/SQL-4479A1?logo=postgresql&logoColor=white)
![HTML5](https://img.shields.io/badge/HTML5-E34F26?logo=html5&logoColor=white)
![CSS3](https://img.shields.io/badge/CSS3-1572B6?logo=css3&logoColor=white)
![Bash](https://img.shields.io/badge/Bash-4EAA25?logo=gnubash&logoColor=white)
![HCL](https://img.shields.io/badge/HCL-844FBA?logo=terraform&logoColor=white)

**Frontend**

![React](https://img.shields.io/badge/React-20232A?logo=react&logoColor=61DAFB)
![React Router](https://img.shields.io/badge/React_Router-CA4245?logo=reactrouter&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-646CFF?logo=vite&logoColor=white)
![Node.js](https://img.shields.io/badge/Node.js-339933?logo=nodedotjs&logoColor=white)
![npm](https://img.shields.io/badge/npm-CB3837?logo=npm&logoColor=white)
![Nginx](https://img.shields.io/badge/Nginx-009639?logo=nginx&logoColor=white)
![Vitest](https://img.shields.io/badge/Vitest-6E9F18?logo=vitest&logoColor=white)
![Testing Library](https://img.shields.io/badge/Testing_Library-E33332?logo=testinglibrary&logoColor=white)
![ESLint](https://img.shields.io/badge/ESLint-4B32C3?logo=eslint&logoColor=white)

**Backend and API**

![Spring Boot](https://img.shields.io/badge/Spring_Boot-6DB33F?logo=springboot&logoColor=white)
![Spring Web MVC](https://img.shields.io/badge/Spring_Web_MVC-6DB33F?logo=spring&logoColor=white)
![Spring Data JPA](https://img.shields.io/badge/Spring_Data_JPA-6DB33F?logo=spring&logoColor=white)
![REST API](https://img.shields.io/badge/REST_API-009688?logoColor=white)
![Hibernate](https://img.shields.io/badge/Hibernate-59666C?logo=hibernate&logoColor=white)
![Bean Validation](https://img.shields.io/badge/Bean_Validation-6DB33F?logo=spring&logoColor=white)
![Flyway](https://img.shields.io/badge/Flyway-CC0200?logo=flyway&logoColor=white)
![Maven](https://img.shields.io/badge/Maven-C71A36?logo=apachemaven&logoColor=white)
![JUnit](https://img.shields.io/badge/JUnit-25A162?logo=junit5&logoColor=white)

**Data and storage**

![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)
![PostGIS](https://img.shields.io/badge/PostGIS-336791?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?logo=redis&logoColor=white)
![MinIO](https://img.shields.io/badge/MinIO-C72E49?logo=minio&logoColor=white)
![Amazon S3](https://img.shields.io/badge/Amazon_S3-569A31?logo=amazons3&logoColor=white)
![NetCDF](https://img.shields.io/badge/NetCDF-0E4C92?logoColor=white)
![GeoTIFF](https://img.shields.io/badge/GeoTIFF-2E7D32?logoColor=white)

**ML and data science**

![XGBoost](https://img.shields.io/badge/XGBoost-EC6B23?logo=xgboost&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-F7931E?logo=scikitlearn&logoColor=white)
![NumPy](https://img.shields.io/badge/NumPy-013243?logo=numpy&logoColor=white)
![xarray](https://img.shields.io/badge/xarray-0E4C92?logo=xarray&logoColor=white)
![rasterio](https://img.shields.io/badge/rasterio-2E7D32?logoColor=white)
![Google Gemini](https://img.shields.io/badge/Google_Gemini-8E75B2?logo=googlegemini&logoColor=white)
![NASA FIRMS](https://img.shields.io/badge/NASA_FIRMS-0B3D91?logo=nasa&logoColor=white)
![Copernicus](https://img.shields.io/badge/Copernicus-003399?logoColor=white)
![ERA5-Land](https://img.shields.io/badge/ERA5--Land-003399?logoColor=white)
![ESA WorldCover](https://img.shields.io/badge/ESA_WorldCover-0B3D91?logoColor=white)

**Containers and orchestration**

![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Docker_Compose-2496ED?logo=docker&logoColor=white)
![Kubernetes](https://img.shields.io/badge/Kubernetes-326CE5?logo=kubernetes&logoColor=white)
![kind](https://img.shields.io/badge/kind-326CE5?logo=kubernetes&logoColor=white)
![Helm](https://img.shields.io/badge/Helm-0F1689?logo=helm&logoColor=white)
![KEDA](https://img.shields.io/badge/KEDA-326CE5?logo=keda&logoColor=white)
![HPA](https://img.shields.io/badge/HPA-326CE5?logo=kubernetes&logoColor=white)

**Cloud and infrastructure as code**

![Terraform](https://img.shields.io/badge/Terraform-844FBA?logo=terraform&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-232F3E?logo=amazonaws&logoColor=white)
![VPC](https://img.shields.io/badge/VPC-8C4FFF?logo=amazonvpc&logoColor=white)
![EKS](https://img.shields.io/badge/EKS-FF9900?logo=amazoneks&logoColor=white)
![RDS](https://img.shields.io/badge/RDS-527FFF?logo=amazonrds&logoColor=white)
![ElastiCache](https://img.shields.io/badge/ElastiCache-C925D1?logo=amazonelasticache&logoColor=white)
![ECR](https://img.shields.io/badge/ECR-FF9900?logo=amazonecs&logoColor=white)
![S3](https://img.shields.io/badge/S3-569A31?logo=amazons3&logoColor=white)
![ALB](https://img.shields.io/badge/ALB-8C4FFF?logo=awselasticloadbalancing&logoColor=white)
![ACM](https://img.shields.io/badge/ACM-DD344C?logo=awscertificatemanager&logoColor=white)
![Route 53](https://img.shields.io/badge/Route_53-8C4FFF?logo=amazonroute53&logoColor=white)
![Secrets Manager](https://img.shields.io/badge/Secrets_Manager-DD344C?logo=awssecretsmanager&logoColor=white)
![External Secrets](https://img.shields.io/badge/External_Secrets-0F1689?logo=kubernetes&logoColor=white)
![CloudWatch](https://img.shields.io/badge/CloudWatch-FF4F8B?logo=amazoncloudwatch&logoColor=white)
![EKS Pod Identity](https://img.shields.io/badge/EKS_Pod_Identity-FF9900?logo=amazoneks&logoColor=white)

**Observability**

![Prometheus](https://img.shields.io/badge/Prometheus-E6522C?logo=prometheus&logoColor=white)
![Micrometer](https://img.shields.io/badge/Micrometer-6DB33F?logo=micrometer&logoColor=white)
![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-425CC7?logo=opentelemetry&logoColor=white)
![Jaeger](https://img.shields.io/badge/Jaeger-66CFE3?logo=jaeger&logoColor=white)
![Structured Logging](https://img.shields.io/badge/Structured_Logging-555555?logo=elastic&logoColor=white)

**CI, quality and security**

![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?logo=githubactions&logoColor=white)
![Trivy](https://img.shields.io/badge/Trivy-1904DA?logo=trivy&logoColor=white)
![Ruff](https://img.shields.io/badge/Ruff-D7FF64?logo=ruff&logoColor=black)
![mypy](https://img.shields.io/badge/mypy-2A6DB2?logo=python&logoColor=white)
![pytest](https://img.shields.io/badge/pytest-0A9EDC?logo=pytest&logoColor=white)
![uv](https://img.shields.io/badge/uv-DE5FE9?logo=uv&logoColor=white)
![Git](https://img.shields.io/badge/Git-F05032?logo=git&logoColor=white)
![GitHub](https://img.shields.io/badge/GitHub-181717?logo=github&logoColor=white)

</div>

## Architecture

```text
React + TypeScript
      |
Java / Spring Boot
      |
   +--+------------------+
   |                      |
sync (analysis,      async (forecast)
 ask-earth)                |
   |                      Redis -> Python workers
   |                      |
   +----------> PostGIS / Object Storage -> Earth data sources
```

A natural-language question first passes through an LLM planner and a deterministic validator before it reaches this pipeline.

## Prerequisites

- Docker Desktop or Docker Engine with Docker Compose v2.
- A NASA FIRMS map key (`FIRMS_MAP_KEY`) to fetch fire data.
- A Gemini API key (`GEMINI_API_KEY`) for the natural-language planner.
- A Copernicus CDS key (`CDSAPI_KEY`) if you want to download ERA5-Land weather data.
- For local development without Docker: JDK 21, Node.js, and Python 3.12 with [uv](https://docs.astral.sh/uv/).

## Quick Start with Docker

1. Create the environment file and fill in your keys.

   ```bash
   cp .env.example .env
   ```

2. Start all services.

   ```bash
   cd infra/docker
   docker compose up -d --build
   ```

3. Check that the backend is ready.

   ```bash
   curl http://localhost:8080/readyz
   ```

4. Open the application.

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8080 |
| Readiness and metrics | http://localhost:8081/actuator/health/readiness |
| Jaeger UI | http://localhost:16686 |
| MinIO console | http://localhost:9001 |

To stop all containers and remove their volumes, run `docker compose down -v` from `infra/docker`.

## Local Development

The frontend and backend can run outside Docker against the same `docker compose` services for Postgres, Redis, and MinIO.

Start only the infrastructure services:

```bash
cd infra/docker
docker compose up -d postgres redis minio
```

Run the backend:

```bash
cd backend
./mvnw spring-boot:run
```

Run the frontend:

```bash
cd frontend
npm ci
npm run dev
```

## Environment Variables

The `.env` file holds the API keys for the data sources and the planner. The backend reads its other settings from `backend/src/main/resources/application.properties`, and each one can be overridden with an environment variable.

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | API key for the natural-language planner. |
| `FIRMS_MAP_KEY` | NASA FIRMS key used to download fire detections. |
| `CDSAPI_URL`, `CDSAPI_KEY` | Copernicus Climate Data Store credentials for ERA5-Land. |
| `SPRING_DATASOURCE_URL` | JDBC URL of the database. The default is `jdbc:postgresql://localhost:5432/ai_earth`. |
| `REDIS_HOST`, `REDIS_PORT` | Redis location. The defaults are `127.0.0.1` and `6379`. |
| `OBJECT_STORE_ENDPOINT`, `OBJECT_STORE_BUCKET` | MinIO or S3 endpoint and bucket. |
| `OBJECT_STORE_ACCESS_KEY`, `OBJECT_STORE_SECRET_KEY` | Object storage credentials. |
| `RATE_LIMIT_FORECASTS_PER_MINUTE`, `RATE_LIMIT_ANALYSES_PER_MINUTE`, `RATE_LIMIT_QUERIES_PER_MINUTE` | Per-client request limits. The defaults are 10, 30, and 20. |
| `FORECAST_WORKER_MAX_ATTEMPTS` | How many times a failed forecast job is retried. The default is 3. |
| `LOG_FORMAT` | Log format. The default is `ecs` (structured JSON). |

Do not commit the `.env` file. It is already excluded by `.gitignore`.

## REST API

| Method | Endpoint | Description |
|---|---|---|
| POST | `/queries` | Ask a natural-language question. |
| GET | `/queries/{id}` | Get the status of a question. |
| GET | `/queries/{id}/result` | Get the answer and its evidence. |
| POST | `/analyses` | Run a fire-history analysis for a region and time range. |
| GET | `/analyses/{id}` | Get an analysis. |
| POST | `/forecasts` | Submit a 24-hour wildfire-risk forecast job. |
| GET | `/forecasts/{id}` | Get the status of a forecast job. |
| GET | `/forecasts/{id}/result` | Get the forecast result. |
| GET | `/results/{id}` | Get a stored result by ID. |
| GET | `/readyz` | Check that the backend, database, and Redis are ready. |

Request and response bodies use snake_case field names. The full contracts are in [`docs/forecast-api-contract.md`](docs/forecast-api-contract.md) and [`docs/ask-earth.md`](docs/ask-earth.md).

## Project Structure

```text
.
|-- backend/      # Spring Boot API, JPA entities, Flyway migrations
|-- frontend/     # React + Vite app
|-- ml/           # Python package for data, features, models, planner, and distributed runs
|-- scripts/      # Data download, benchmark, and demo scripts
|-- infra/        # docker, k8s, kind, and terraform
|-- docs/         # Architecture, contracts, and benchmark write-ups
|-- portfolio/    # Self-contained evidence package
`-- data/         # Raw and processed datasets
```

## Deployment

The `infra/` directory holds three deployment targets. `infra/docker` is the Docker Compose stack used in the quick start. `infra/k8s` and `infra/kind` contain Kubernetes manifests that can be tried locally on a kind cluster. `infra/terraform` defines the AWS deployment in `us-west-2`, with separate modules for the network, EKS, database, cache, storage, registry, secrets, and TLS.

The Terraform code is complete and passes `fmt`, `validate`, and a Trivy security scan. It has not been applied to a live AWS account yet, because the environment costs about $0.40 per hour to run. See [`docs/cloud-deployment.md`](docs/cloud-deployment.md) and [`docs/terraform-layout.md`](docs/terraform-layout.md) for the details.

## Results

![Measured results page](docs/images/results.png)

- **Model accuracy.** The XGBoost model reaches a PR-AUC of 0.4513, compared with 0.2522 for the climatology baseline.
- **Ablation.** Adding terrain and land cover improves PR-AUC by 0.081 over fire history and weather alone.
- **Distributed recovery.** After a worker was killed, no tiles were lost and the system recovered in 1.35 seconds.
- **Planner accuracy.** The planner got intent, region, and execution right on all 14 live test questions.

The full detail, including the mixed and negative findings, is in [`docs/headline-results.md`](docs/headline-results.md). Nothing is left out because it did not clear a headline bar.

## Testing

```bash
cd backend && ./mvnw test                # needs docker compose up -d first
uv run --project ml pytest ml/tests -q   # from repo root
cd frontend && npm test
```

The last full run passed 177 backend, 539 ML, and 49 frontend tests, 765 in total. There is no mocked-datasource tier, so every backend test runs against a real Postgres, Redis, and MinIO.

## Security Notes

- The LLM only produces a plan. A deterministic validator checks the plan against a fixed set of tools before anything executes.
- The backend limits request size, rate-limits each endpoint, redacts secrets from logs, and sets security headers.
- The API does not authenticate users yet, so do not expose it publicly without adding authentication in front of it.
- The default database and object storage passwords in the Compose files are for local development only. Replace them before any real deployment.

## Docs

- [`docs/`](docs/) describes the architecture, data contracts, API contracts, benchmarks, and deployment in full detail.
- [`docs/headline-results.md`](docs/headline-results.md) lists the measured results, including the negative and mixed findings.
- [`portfolio/`](portfolio/) is a self-contained evidence package for a reader who does not know the rest of the repository.

## Contributing

This is a personal project, built end to end by one person. Issues and suggestions are welcome. Open a pull request if you would like to contribute a fix or improvement.

| Name | Role | Github |
|---|---|---|
| Khoa Ho Nguyen | Author and maintainer | [@khoahonguyen0210](https://github.com/khoahonguyen0210) |

## License

This project is released under the MIT license. See [`LICENSE`](LICENSE).
