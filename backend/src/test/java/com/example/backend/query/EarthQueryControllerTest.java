package com.example.backend.query;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.example.backend.logging.ErrorCode;
import com.example.backend.logging.SecretRedactor;
import com.example.backend.region.RegionStore;
import com.example.backend.tracing.Spans;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import tools.jackson.databind.ObjectMapper;

class EarthQueryControllerTest {

    private static final EarthQueryRequest VALID_REQUEST =
            new EarthQueryRequest("How many fires occurred in California in August 2024?");

    private static class StubRunner implements EarthQueryRunner {
        private final EarthQueryOutcome outcome;

        StubRunner(EarthQueryOutcome outcome) {
            this.outcome = outcome;
        }

        @Override
        public EarthQueryOutcome run(EarthQueryRequest request) {
            return outcome;
        }
    }

    private static EarthQueryController newController(EarthQueryRunner runner) {
        return new EarthQueryController(
                runner, newStore(), SecretRedactor.of(), new SimpleMeterRegistry(), Spans.noop(), RegionStore.noop());
    }

    private static EarthQueryStore newStore() {
        EarthQueryJpaRepository repository = mock(EarthQueryJpaRepository.class);
        Map<String, EarthQueryEntity> backing = new HashMap<>();

        when(repository.save(any())).thenAnswer(invocation -> {
            EarthQueryEntity entity = invocation.getArgument(0);
            backing.put(entity.getId(), entity);
            return entity;
        });
        when(repository.findById(any())).thenAnswer(
                invocation -> Optional.ofNullable(backing.get(invocation.getArgument(0))));

        return new EarthQueryStore(repository, new ObjectMapper(), Spans.noop());
    }

    private static Map<String, Object> sampleResult() {
        return Map.of(
                "question", "How many fires occurred in California in August 2024?",
                "answer", "There were 42 fires (computed).",
                "facts", java.util.List.of(Map.of("step_id", "count", "category", "computed")),
                "outputs", Map.of("count", Map.of("count", 42)),
                "plan", Map.of("steps", java.util.List.of()));
    }

    @Test
    void createQueryReturnsCreatedWithSucceededStatus() {
        StubRunner runner = new StubRunner(EarthQueryOutcome.success(sampleResult()));
        EarthQueryController controller = newController(runner);

        ResponseEntity<EarthQueryController.EarthQuerySummaryResponse> response = controller.createQuery(VALID_REQUEST);

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("SUCCEEDED", response.getBody().status());
        assertNotNull(response.getBody().id());
    }

    @Test
    void createQueryReturnsFailedStatusOnRunnerError() {
        StubRunner runner = new StubRunner(EarthQueryOutcome.failure(ErrorCode.PYTHON_FAILED, "the planner refused to answer"));
        EarthQueryController controller = newController(runner);

        ResponseEntity<EarthQueryController.EarthQuerySummaryResponse> response = controller.createQuery(VALID_REQUEST);

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertEquals("FAILED", response.getBody().status());
    }

    @Test
    void getQueryReturnsStoredStatusById() {
        StubRunner runner = new StubRunner(EarthQueryOutcome.success(sampleResult()));
        EarthQueryController controller = newController(runner);

        String id = controller.createQuery(VALID_REQUEST).getBody().id();
        ResponseEntity<EarthQueryController.EarthQuerySummaryResponse> response = controller.getQuery(id);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(id, response.getBody().id());
        assertEquals("SUCCEEDED", response.getBody().status());
    }

    @Test
    void getQueryReturnsNotFoundForUnknownId() {
        EarthQueryController controller = newController(new StubRunner(EarthQueryOutcome.success(sampleResult())));

        ResponseEntity<EarthQueryController.EarthQuerySummaryResponse> response = controller.getQuery("does-not-exist");

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    }

    @Test
    void getResultReturnsTheWholePayloadOnSuccess() {
        Map<String, Object> result = sampleResult();
        StubRunner runner = new StubRunner(EarthQueryOutcome.success(result));
        EarthQueryController controller = newController(runner);

        String id = controller.createQuery(VALID_REQUEST).getBody().id();
        ResponseEntity<?> response = controller.getResult(id);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        EarthQueryController.ResultResponse body = (EarthQueryController.ResultResponse) response.getBody();
        assertEquals(result, body.result());
    }

    @Test
    void getResultReturnsErrorPayloadOnFailure() {
        StubRunner runner = new StubRunner(EarthQueryOutcome.failure(ErrorCode.PYTHON_FAILED, "boom"));
        EarthQueryController controller = newController(runner);

        String id = controller.createQuery(VALID_REQUEST).getBody().id();
        ResponseEntity<?> response = controller.getResult(id);

        assertEquals(422, response.getStatusCode().value());
        EarthQueryController.ErrorResponse body = (EarthQueryController.ErrorResponse) response.getBody();
        assertEquals("boom", body.error());
    }

    @Test
    void aFailedQueryStoresAndReturnsItsErrorRedacted() {
        String secret = "firms-map-key-0123456789";
        EarthQueryController controller = new EarthQueryController(
                new StubRunner(EarthQueryOutcome.failure(ErrorCode.PYTHON_FAILED,
                        "HTTPError for https://firms.modaps.eosdis.nasa.gov/api/area/csv/" + secret + "/x")),
                newStore(), SecretRedactor.of(secret), new SimpleMeterRegistry(), Spans.noop(), RegionStore.noop());

        String id = controller.createQuery(VALID_REQUEST).getBody().id();
        EarthQueryController.ErrorResponse body = (EarthQueryController.ErrorResponse) controller.getResult(id).getBody();

        assertEquals("HTTPError for https://firms.modaps.eosdis.nasa.gov/api/area/csv/***/x", body.error());
    }

    @Test
    void getResultReturnsNotFoundForUnknownId() {
        EarthQueryController controller = newController(new StubRunner(EarthQueryOutcome.success(sampleResult())));

        ResponseEntity<?> response = controller.getResult("does-not-exist");

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    }

    @Test
    void earthQueryStoreRoundTripsSavedQuery() {
        EarthQueryStore store = newStore();
        EarthQuery query = EarthQuery.from(
                "test-id", VALID_REQUEST, java.time.Instant.now(), EarthQueryOutcome.success(sampleResult()));

        store.save(query);

        assertTrue(store.find("test-id").isPresent());
        assertEquals("test-id", store.find("test-id").get().id());
        assertTrue(store.find("missing").isEmpty());
    }
}
