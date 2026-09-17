package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.example.backend.logging.ErrorCode;
import com.example.backend.tracing.Spans;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import tools.jackson.databind.ObjectMapper;

class ForecastControllerTest {

    private static final ForecastRequest VALID_REQUEST = new ForecastRequest(
            new ForecastRequest.RegionSpec("named", "california"),
            "2024-08-15T10:00:00Z");

    private static class FakeQueue implements ForecastQueue {
        private final Deque<String> queued = new ArrayDeque<>();

        @Override
        public void enqueue(String forecastId) {
            queued.add(forecastId);
        }

        @Override
        public Optional<String> dequeue() {
            return Optional.ofNullable(queued.poll());
        }

        @Override
        public long size() {
            return queued.size();
        }

        @Override
        public boolean contains(String forecastId) {
            return queued.contains(forecastId);
        }
    }

    private static ForecastStore newStore() {
        return InMemoryForecasts.store(Spans.noop());
    }

    @Test
    void createForecastReturnsCreatedWithPendingStatusAndEnqueuesTheJob() {
        FakeQueue queue = new FakeQueue();
        ForecastController controller = new ForecastController(queue, newStore(), Spans.noop());

        ResponseEntity<ForecastController.ForecastSummaryResponse> response =
                controller.createForecast(VALID_REQUEST, null);

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("PENDING", response.getBody().status());
        assertNotNull(response.getBody().forecastId());
        assertEquals(response.getBody().forecastId(), queue.dequeue().orElseThrow());
    }

    @Test
    void getForecastReturnsStoredStatusById() {
        ForecastController controller = new ForecastController(new FakeQueue(), newStore(), Spans.noop());

        String id = controller.createForecast(VALID_REQUEST, null).getBody().forecastId();
        ResponseEntity<ForecastController.ForecastSummaryResponse> response = controller.getForecast(id);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(id, response.getBody().forecastId());
        assertEquals("PENDING", response.getBody().status());
    }

    @Test
    void getForecastReturnsNotFoundForUnknownId() {
        ForecastController controller = new ForecastController(new FakeQueue(), newStore(), Spans.noop());

        ResponseEntity<ForecastController.ForecastSummaryResponse> response = controller.getForecast("does-not-exist");

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    }

    @Test
    void getForecastResultReturnsResultOnSuccess() {
        ForecastStore store = newStore();
        Map<String, Object> result = Map.of("model_version", "v1", "evidence", Map.of("dataset", "wildfire_forecast:v1"));
        Forecast forecast = Forecast.from("test-id", VALID_REQUEST, Instant.now(), ForecastOutcome.success(result));
        store.save(forecast);
        ForecastController controller = new ForecastController(new FakeQueue(), store, Spans.noop());

        ResponseEntity<?> response = controller.getForecastResult("test-id");

        assertEquals(HttpStatus.OK, response.getStatusCode());
        ForecastController.ForecastResultResponse body = (ForecastController.ForecastResultResponse) response.getBody();
        assertEquals(result, body.result());
    }

    @Test
    void getForecastResultReturnsErrorPayloadOnFailure() {
        ForecastStore store = newStore();
        Forecast forecast = Forecast.from("test-id", VALID_REQUEST, Instant.now(), ForecastOutcome.failure(ErrorCode.PYTHON_FAILED, "boom"));
        store.save(forecast);
        ForecastController controller = new ForecastController(new FakeQueue(), store, Spans.noop());

        ResponseEntity<?> response = controller.getForecastResult("test-id");

        assertEquals(422, response.getStatusCode().value());
        ForecastController.ErrorResponse body = (ForecastController.ErrorResponse) response.getBody();
        assertEquals("boom", body.error());
    }

    @Test
    void getForecastResultReturnsConflictWhileNotYetFinished() {
        ForecastController controller = new ForecastController(new FakeQueue(), newStore(), Spans.noop());

        String id = controller.createForecast(VALID_REQUEST, null).getBody().forecastId();
        ResponseEntity<?> response = controller.getForecastResult(id);

        assertEquals(409, response.getStatusCode().value());
        ForecastController.ErrorResponse body = (ForecastController.ErrorResponse) response.getBody();
        assertTrue(body.error().contains("PENDING"));
    }

    @Test
    void getForecastResultReturnsNotFoundForUnknownId() {
        ForecastController controller = new ForecastController(new FakeQueue(), newStore(), Spans.noop());

        ResponseEntity<?> response = controller.getForecastResult("does-not-exist");

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    }

    @Test
    void forecastStoreRoundTripsSavedForecast() {
        ForecastStore store = newStore();
        Forecast forecast = Forecast.from(
                "test-id", VALID_REQUEST, Instant.now(), ForecastOutcome.success(Map.of("model_version", "v1")));

        store.save(forecast);

        assertTrue(store.find("test-id").isPresent());
        assertEquals("test-id", store.find("test-id").get().id());
        assertTrue(store.find("missing").isEmpty());
    }

    @Test
    void createForecastWithSameIdempotencyKeyReturnsTheExistingJobWithoutEnqueueingAgain() {
        FakeQueue queue = new FakeQueue();
        ForecastController controller = new ForecastController(queue, newStore(), Spans.noop());

        ResponseEntity<ForecastController.ForecastSummaryResponse> first =
                controller.createForecast(VALID_REQUEST, "dup-key");
        ResponseEntity<ForecastController.ForecastSummaryResponse> second =
                controller.createForecast(VALID_REQUEST, "dup-key");

        assertEquals(HttpStatus.CREATED, first.getStatusCode());
        assertEquals(HttpStatus.OK, second.getStatusCode());
        assertEquals(first.getBody().forecastId(), second.getBody().forecastId());
        assertNotNull(queue.dequeue().orElse(null));
        assertTrue(queue.dequeue().isEmpty(), "the second call must not enqueue a second job");
    }

    @Test
    void createForecastWithDifferentIdempotencyKeysCreatesSeparateJobs() {
        ForecastController controller = new ForecastController(new FakeQueue(), newStore(), Spans.noop());

        String firstId = controller.createForecast(VALID_REQUEST, "key-a").getBody().forecastId();
        String secondId = controller.createForecast(VALID_REQUEST, "key-b").getBody().forecastId();

        assertNotEquals(firstId, secondId);
    }

    @Test
    void createForecastWithoutAnIdempotencyKeyAlwaysCreatesASeparateJob() {
        ForecastController controller = new ForecastController(new FakeQueue(), newStore(), Spans.noop());

        String firstId = controller.createForecast(VALID_REQUEST, null).getBody().forecastId();
        String secondId = controller.createForecast(VALID_REQUEST, null).getBody().forecastId();

        assertNotEquals(firstId, secondId);
    }

    @Test
    void createForecastRecoversFromALostIdempotencyRace() {
        ForecastJpaRepository repository = mock(ForecastJpaRepository.class);
        ObjectMapper objectMapper = new ObjectMapper();
        ForecastEntity winnerEntity = new ForecastEntity(
                "winner-id",
                objectMapper.writeValueAsString(VALID_REQUEST),
                "PENDING",
                null,
                null,
                Instant.now(),
                0,
                "race-key",
                null,
                Instant.now());

        when(repository.findByIdempotencyKey("race-key"))
                .thenReturn(Optional.empty())
                .thenReturn(Optional.of(winnerEntity));
        when(repository.save(any())).thenThrow(new DataIntegrityViolationException("duplicate idempotency key"));

        ForecastController controller = new ForecastController(new FakeQueue(), new ForecastStore(repository, objectMapper, Spans.noop()), Spans.noop());

        ResponseEntity<ForecastController.ForecastSummaryResponse> response =
                controller.createForecast(VALID_REQUEST, "race-key");

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("winner-id", response.getBody().forecastId());
    }
}
