package com.example.backend.analysis;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

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

    @Test
    void createAnalysisReturnsCreatedWithSucceededStatus() {
        StubRunner runner = new StubRunner(AnalysisOutcome.success(Map.of("count", 42), Map.of("dataset", "NASA_FIRMS")));
        AnalysisStore store = new AnalysisStore();
        AnalysisController controller = new AnalysisController(runner, store);

        ResponseEntity<AnalysisController.AnalysisSummaryResponse> response = controller.createAnalysis(VALID_REQUEST);

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("SUCCEEDED", response.getBody().status());
        assertNotNull(response.getBody().id());
    }

    @Test
    void createAnalysisReturnsFailedStatusOnRunnerError() {
        StubRunner runner = new StubRunner(AnalysisOutcome.failure("Unsupported operation: 'forecast'"));
        AnalysisStore store = new AnalysisStore();
        AnalysisController controller = new AnalysisController(runner, store);

        ResponseEntity<AnalysisController.AnalysisSummaryResponse> response = controller.createAnalysis(VALID_REQUEST);

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertEquals("FAILED", response.getBody().status());
    }

    @Test
    void getAnalysisReturnsStoredStatusById() {
        StubRunner runner = new StubRunner(AnalysisOutcome.success(Map.of("count", 42), Map.of()));
        AnalysisStore store = new AnalysisStore();
        AnalysisController controller = new AnalysisController(runner, store);

        String id = controller.createAnalysis(VALID_REQUEST).getBody().id();
        ResponseEntity<AnalysisController.AnalysisSummaryResponse> response = controller.getAnalysis(id);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(id, response.getBody().id());
        assertEquals("SUCCEEDED", response.getBody().status());
    }

    @Test
    void getAnalysisReturnsNotFoundForUnknownId() {
        AnalysisStore store = new AnalysisStore();
        AnalysisController controller = new AnalysisController(new StubRunner(AnalysisOutcome.success(null, null)), store);

        ResponseEntity<AnalysisController.AnalysisSummaryResponse> response = controller.getAnalysis("does-not-exist");

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    }

    @Test
    void getResultReturnsResultAndEvidenceOnSuccess() {
        Map<String, Object> result = Map.of("count", 42);
        Map<String, Object> evidence = Map.of("dataset", "NASA_FIRMS");
        StubRunner runner = new StubRunner(AnalysisOutcome.success(result, evidence));
        AnalysisStore store = new AnalysisStore();
        AnalysisController controller = new AnalysisController(runner, store);

        String id = controller.createAnalysis(VALID_REQUEST).getBody().id();
        ResponseEntity<?> response = controller.getResult(id);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        AnalysisController.ResultResponse body = (AnalysisController.ResultResponse) response.getBody();
        assertEquals(result, body.result());
        assertEquals(evidence, body.evidence());
    }

    @Test
    void getResultReturnsErrorPayloadOnFailure() {
        StubRunner runner = new StubRunner(AnalysisOutcome.failure("boom"));
        AnalysisStore store = new AnalysisStore();
        AnalysisController controller = new AnalysisController(runner, store);

        String id = controller.createAnalysis(VALID_REQUEST).getBody().id();
        ResponseEntity<?> response = controller.getResult(id);

        assertEquals(422, response.getStatusCode().value());
        AnalysisController.ErrorResponse body = (AnalysisController.ErrorResponse) response.getBody();
        assertEquals("boom", body.error());
    }

    @Test
    void getResultReturnsNotFoundForUnknownId() {
        AnalysisStore store = new AnalysisStore();
        AnalysisController controller = new AnalysisController(new StubRunner(AnalysisOutcome.success(null, null)), store);

        ResponseEntity<?> response = controller.getResult("does-not-exist");

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    }

    @Test
    void analysisStoreRoundTripsSavedAnalysis() {
        AnalysisStore store = new AnalysisStore();
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
