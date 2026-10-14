package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@SpringBootTest(properties = {
        "forecast.store=dynamodb",
        "dynamodb.forecast-table=forecast-jobs-wiring-test",
        "dynamodb.create-table=true",
        "dynamodb.access-key=local",
        "dynamodb.secret-key=local",
        "forecast.recovery.interval-seconds=3600"
})
class DynamoDbStoreWiringTest {

    @DynamicPropertySource
    static void endpoint(DynamicPropertyRegistry registry) {
        registry.add("dynamodb.endpoint",
                () -> Optional.ofNullable(System.getenv("DYNAMODB_ENDPOINT")).orElse("http://localhost:8000"));
    }

    @Autowired
    private ForecastStore store;

    @Test
    void theDynamoDbStoreServesForecastsWhenSelected() {
        assertInstanceOf(DynamoDbForecastStore.class, store);

        String id = UUID.randomUUID().toString();
        store.save(Forecast.pending(id, ForecastStoreContract.REQUEST, Instant.now()));

        assertTrue(store.find(id).isPresent());
    }
}
