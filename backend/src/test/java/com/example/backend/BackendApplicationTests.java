package com.example.backend;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

/**
 * Real JPA entities (AnalysisEntity/ForecastEntity) back this context, so it
 * genuinely needs a live datasource -- run `docker compose up -d` in
 * infra/docker/ before running this test (see docs/persistence-schema.md).
 * Excluding DataSourceAutoConfiguration would break JPA repository startup
 * rather than avoid it, so it must stay enabled here.
 */
@SpringBootTest
class BackendApplicationTests {

    @Test
    void contextLoads() {
    }

}
