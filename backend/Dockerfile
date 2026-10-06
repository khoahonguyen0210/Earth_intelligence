FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY backend/pom.xml .
RUN mvn -B dependency:go-offline
COPY backend/src ./src
RUN mvn -B package -DskipTests

FROM eclipse-temurin:21-jre-jammy
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

COPY ml/pyproject.toml ml/uv.lock ./ml/
COPY ml/src ./ml/src
RUN cd ml && uv sync --frozen

COPY scripts ./scripts
COPY data/raw ./data/raw
COPY ml/artifacts/production_model_v1 ./ml/artifacts/production_model_v1
COPY ml/artifacts/docs_index_v1 ./ml/artifacts/docs_index_v1

COPY --from=build /build/target/*.jar app.jar

ENV FORECAST_PYTHON_EXECUTABLE=/app/ml/.venv/bin/python \
    ANALYSIS_PYTHON_EXECUTABLE=/app/ml/.venv/bin/python \
    ASK_EARTH_PYTHON_EXECUTABLE=/app/ml/.venv/bin/python \
    FORECAST_PYTHON_WORKDIR=/app \
    ANALYSIS_PYTHON_WORKDIR=/app \
    ASK_EARTH_PYTHON_WORKDIR=/app

EXPOSE 8080 8081
ENTRYPOINT ["java", "-jar", "app.jar"]
