# Multi-stage: build the Spring Boot jar, then bundle it with the Python
# + ml/ environment PythonForecastRunner/PythonAnalysisRunner
# need for their subprocess bridge. See docs/docker-images.md for why
# this one image plays both the "backend" and "python-worker" roles --
# the real bridge (ProcessBuilder) is a
# same-machine subprocess call, not a network call, so there is no
# separate networked service to containerize on its own.
#
# Build from the repository root, not this directory:
#   docker build -f backend/Dockerfile .
# (infra/docker/docker-compose.yml's own build context already does this.)

FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY backend/pom.xml .
RUN mvn -B dependency:go-offline
COPY backend/src ./src
RUN mvn -B package -DskipTests

FROM eclipse-temurin:21-jre-jammy
WORKDIR /app

# curl: docker-compose.yml's own healthcheck against /actuator/health --
# not present in this base image by default.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# uv manages its own Python interpreter version -- nothing here needs to
# separately track ml/pyproject.toml's ">=3.12" requirement against
# whatever Python the base image's package manager happens to ship.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

COPY ml/pyproject.toml ml/uv.lock ./ml/
COPY ml/src ./ml/src
RUN cd ml && uv sync --frozen

COPY scripts ./scripts
# data/raw now holds the real fire-season history the forecast path reads
# (docs/historical-dataset.md); the trained production model is baked in
# beside it, so a container never trains at request time.
COPY data/raw ./data/raw
COPY ml/artifacts/production_model_v1 ./ml/artifacts/production_model_v1
COPY ml/artifacts/docs_index_v1 ./ml/artifacts/docs_index_v1

COPY --from=build /build/target/*.jar app.jar

# Points application.properties' existing overridable placeholders
# (forecast.python.*/analysis.python.*) at this image's own venv and
# working directory -- no Java code change needed for containerization.
ENV FORECAST_PYTHON_EXECUTABLE=/app/ml/.venv/bin/python \
    ANALYSIS_PYTHON_EXECUTABLE=/app/ml/.venv/bin/python \
    ASK_EARTH_PYTHON_EXECUTABLE=/app/ml/.venv/bin/python \
    FORECAST_PYTHON_WORKDIR=/app \
    ANALYSIS_PYTHON_WORKDIR=/app \
    ASK_EARTH_PYTHON_WORKDIR=/app

# 8081 is the internal management port (actuator), never published.
EXPOSE 8080 8081
ENTRYPOINT ["java", "-jar", "app.jar"]
