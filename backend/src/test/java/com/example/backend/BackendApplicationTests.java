package com.example.backend;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

/**
 * Since Task 6.3, real JPA entities (AnalysisEntity/ForecastEntity) exist,
 * so the full context now genuinely needs a live datasource -- run
 * `docker compose up -d` in infra/docker/ before running this test (see
 * docs/persistence-schema.md). The earlier DataSourceAutoConfiguration
 * exclusion is gone: excluding it now would break JPA repository startup
 * instead of avoiding it.
 */
@SpringBootTest
class BackendApplicationTests {

    @Test
    void contextLoads() {
    }

}
