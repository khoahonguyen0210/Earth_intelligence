package com.example.backend.analysis;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.example.backend.logging.ErrorCode;
import com.example.backend.logging.SecretRedactor;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import tools.jackson.databind.ObjectMapper;

class AnalysisControllerTest {

    private static final AnalysisRequest VALID_REQUEST = new AnalysisRequest(
            "How many fires in California?",
            "count",
            new AnalysisRequest.RegionSpec("named", "california"),
            new AnalysisRequest.TimeRangeSpec("2024-08-01", "2024-08-07"),
            "count");

    private static class StubRunner implements AnalysisRunner {
        private final AnalysisOutcome outcome;

        StubRunner(AnalysisOutcome outcome) {
            this.outcome = outcome;
        }

        @Override
        public AnalysisOutcome run(AnalysisRequest request) {
            return outcome;
        }
    }

    /**
     * AnalysisStore is now Postgres-backed (Task 6.3); these tests stay
     * DB-free by faking the JpaRepository with an in-memory map behind a
     * Mockito mock, exercising the store's real JSON conversion logic.
     */
    private static AnalysisController newController(AnalysisRunner runner) {
        return new AnalysisController(runner, newStore(), SecretRedactor.of(), new SimpleMeterRegistry());
    }

    private static AnalysisStore newStore() {
        AnalysisJpaRepository repository = mock(AnalysisJpaRepository.class);
        Map<String, AnalysisEntity> backing = new HashMap<>();

        when(repository.save(any())).thenAnswer(invocation -> {
            AnalysisEntity entity = invocation.getArgument(0);
            backing.put(entity.getId(), entity);
            return entity;
        });
        when(repository.findById(any())).thenAnswer(
                invocation -> Optional.ofNullable(backing.get(invocation.getArgument(0))));

        return new AnalysisStore(repository, new ObjectMapper());
    }

    @Test
    void createAnalysisReturnsCreatedWithSucceededStatus() {
        StubRunner runner = new StubRunner(AnalysisOutcome.success(Map.of("count", 42), Map.of("dataset", "NASA_FIRMS")));
        AnalysisController controller = newController(runner);

        ResponseEntity<AnalysisController.AnalysisSummaryResponse> response = controller.createAnalysis(VALID_REQUEST);

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("SUCCEEDED", response.getBody().status());
        assertNotNull(response.getBody().id());
    }

    @Test
    void createAnalysisReturnsFailedStatusOnRunnerError() {
        StubRunner runner = new StubRunner(AnalysisOutcome.failure(ErrorCode.PYTHON_FAILED, "Unsupported operation: 'forecast'"));
        AnalysisController controller = newController(runner);

        ResponseEntity<AnalysisController.AnalysisSummaryResponse> response = controller.createAnalysis(VALID_REQUEST);

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertEquals("FAILED", response.getBody().status());
    }

    @Test
    void getAnalysisReturnsStoredStatusById() {
        StubRunner runner = new StubRunner(AnalysisOutcome.success(Map.of("count", 42), Map.of()));
        AnalysisController controller = newController(runner);

        String id = controller.createAnalysis(VALID_REQUEST).getBody().id();
        ResponseEntity<AnalysisController.AnalysisSummaryResponse> response = controller.getAnalysis(id);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(id, response.getBody().id());
        assertEquals("SUCCEEDED", response.getBody().status());
    }

    @Test
    void getAnalysisReturnsNotFoundForUnknownId() {
        AnalysisController controller = newController(new StubRunner(AnalysisOutcome.success(null, null)));

        ResponseEntity<AnalysisController.AnalysisSummaryResponse> response = controller.getAnalysis("does-not-exist");

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    }

    @Test
    void getResultReturnsResultAndEvidenceOnSuccess() {
        Map<String, Object> result = Map.of("count", 42);
        Map<String, Object> evidence = Map.of("dataset", "NASA_FIRMS");
        StubRunner runner = new StubRunner(AnalysisOutcome.success(result, evidence));
        AnalysisController controller = newController(runner);

        String id = controller.createAnalysis(VALID_REQUEST).getBody().id();
        ResponseEntity<?> response = controller.getResult(id);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        AnalysisController.ResultResponse body = (AnalysisController.ResultResponse) response.getBody();
        assertEquals(result, body.result());
        assertEquals(evidence, body.evidence());
    }

    @Test
    void getResultReturnsErrorPayloadOnFailure() {
        StubRunner runner = new StubRunner(AnalysisOutcome.failure(ErrorCode.PYTHON_FAILED, "boom"));
        AnalysisController controller = newController(runner);

        String id = controller.createAnalysis(VALID_REQUEST).getBody().id();
        ResponseEntity<?> response = controller.getResult(id);

        assertEquals(422, response.getStatusCode().value());
        AnalysisController.ErrorResponse body = (AnalysisController.ErrorResponse) response.getBody();
        assertEquals("boom", body.error());
    }

    @Test
    void getResultReturnsNotFoundForUnknownId() {
        AnalysisController controller = newController(new StubRunner(AnalysisOutcome.success(null, null)));

        ResponseEntity<?> response = controller.getResult("does-not-exist");

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    }

    @Test
    void analysisStoreRoundTripsSavedAnalysis() {
        AnalysisStore store = newStore();
        Analysis analysis = Analysis.from(
                "test-id",
                VALID_REQUEST,
                java.time.Instant.now(),
                AnalysisOutcome.success(Map.of("count", 1), Map.of()));

        store.save(analysis);

        assertTrue(store.find("test-id").isPresent());
        assertEquals("test-id", store.find("test-id").get().id());
        assertTrue(store.find("missing").isEmpty());
    }
}
