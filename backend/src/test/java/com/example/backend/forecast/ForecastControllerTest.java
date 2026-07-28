package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import tools.jackson.databind.ObjectMapper;

class ForecastControllerTest {

    private static final ForecastRequest VALID_REQUEST = new ForecastRequest(
            new ForecastRequest.RegionSpec("named", "california"),
            "2024-08-15T10:00:00Z");

    private static class StubRunner implements ForecastRunner {
        private final ForecastOutcome outcome;

        StubRunner(ForecastOutcome outcome) {
            this.outcome = outcome;
        }

        @Override
        public ForecastOutcome run(ForecastRequest request) {
            return outcome;
        }
    }

    /**
     * ForecastStore is now Postgres-backed (Task 6.3); these tests stay
     * DB-free by faking the JpaRepository with an in-memory map behind a
     * Mockito mock, exercising the store's real JSON conversion logic.
     */
    private static ForecastStore newStore() {
        ForecastJpaRepository repository = mock(ForecastJpaRepository.class);
        Map<String, ForecastEntity> backing = new HashMap<>();

        when(repository.save(any())).thenAnswer(invocation -> {
            ForecastEntity entity = invocation.getArgument(0);
            backing.put(entity.getId(), entity);
            return entity;
        });
        when(repository.findById(any())).thenAnswer(
                invocation -> Optional.ofNullable(backing.get(invocation.getArgument(0))));

        return new ForecastStore(repository, new ObjectMapper());
    }

    @Test
    void createForecastReturnsCreatedWithSucceededStatus() {
        StubRunner runner = new StubRunner(ForecastOutcome.success(Map.of("model_version", "v1")));
        ForecastController controller = new ForecastController(runner, newStore());

        ResponseEntity<ForecastController.ForecastSummaryResponse> response = controller.createForecast(VALID_REQUEST);

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("SUCCEEDED", response.getBody().status());
        assertNotNull(response.getBody().forecastId());
    }

    @Test
    void createForecastReturnsFailedStatusOnRunnerError() {
        StubRunner runner = new StubRunner(ForecastOutcome.failure("cannot fit XGBoost: only one class"));
        ForecastController controller = new ForecastController(runner, newStore());

        ResponseEntity<ForecastController.ForecastSummaryResponse> response = controller.createForecast(VALID_REQUEST);

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertEquals("FAILED", response.getBody().status());
    }

    @Test
    void getForecastReturnsStoredStatusById() {
        StubRunner runner = new StubRunner(ForecastOutcome.success(Map.of("model_version", "v1")));
        ForecastController controller = new ForecastController(runner, newStore());

        String id = controller.createForecast(VALID_REQUEST).getBody().forecastId();
        ResponseEntity<ForecastController.ForecastSummaryResponse> response = controller.getForecast(id);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(id, response.getBody().forecastId());
        assertEquals("SUCCEEDED", response.getBody().status());
    }

    @Test
    void getForecastReturnsNotFoundForUnknownId() {
        ForecastController controller = new ForecastController(new StubRunner(ForecastOutcome.success(null)), newStore());

        ResponseEntity<ForecastController.ForecastSummaryResponse> response = controller.getForecast("does-not-exist");

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    }

    @Test
    void getForecastResultReturnsResultOnSuccess() {
        Map<String, Object> result = Map.of("model_version", "v1", "evidence", Map.of("dataset", "wildfire_forecast:v1"));
        StubRunner runner = new StubRunner(ForecastOutcome.success(result));
        ForecastController controller = new ForecastController(runner, newStore());

        String id = controller.createForecast(VALID_REQUEST).getBody().forecastId();
        ResponseEntity<?> response = controller.getForecastResult(id);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        ForecastController.ForecastResultResponse body = (ForecastController.ForecastResultResponse) response.getBody();
        assertEquals(result, body.result());
    }

    @Test
    void getForecastResultReturnsErrorPayloadOnFailure() {
        StubRunner runner = new StubRunner(ForecastOutcome.failure("boom"));
        ForecastController controller = new ForecastController(runner, newStore());

        String id = controller.createForecast(VALID_REQUEST).getBody().forecastId();
        ResponseEntity<?> response = controller.getForecastResult(id);

        assertEquals(422, response.getStatusCode().value());
        ForecastController.ErrorResponse body = (ForecastController.ErrorResponse) response.getBody();
        assertEquals("boom", body.error());
    }

    @Test
    void getForecastResultReturnsNotFoundForUnknownId() {
        ForecastController controller = new ForecastController(new StubRunner(ForecastOutcome.success(null)), newStore());

        ResponseEntity<?> response = controller.getForecastResult("does-not-exist");

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    }

    @Test
    void forecastStoreRoundTripsSavedForecast() {
        ForecastStore store = newStore();
        Forecast forecast = Forecast.from(
                "test-id",
                VALID_REQUEST,
                java.time.Instant.now(),
                ForecastOutcome.success(Map.of("model_version", "v1")));

        store.save(forecast);

        assertTrue(store.find("test-id").isPresent());
        assertEquals("test-id", store.find("test-id").get().id());
        assertTrue(store.find("missing").isEmpty());
    }
}
