package com.example.backend.forecast;

import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.TestPropertySource;

@SpringBootTest
@TestPropertySource(properties = "forecast.recovery.interval-seconds=3600")
class JpaForecastStoreIntegrationTest extends ForecastStoreContract {

    @Autowired
    private ForecastStore store;

    @Autowired
    private JdbcTemplate jdbc;

    @Override
    protected ForecastStore store() {
        return store;
    }

    @Override
    protected void backdate(String id, Duration age) {
        jdbc.update("update forecasts set updated_at = ? where id = ?", Timestamp.from(Instant.now().minus(age)), id);
    }
}
