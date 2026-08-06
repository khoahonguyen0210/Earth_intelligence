package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

/**
 * Task 6.6: PythonForecastRunner's timeout/kill and transient-vs-permanent
 * classification, exercised against the real python interpreter (the same
 * assumption forecast.python.executable already makes, per
 * application.properties) and tiny fixture scripts under
 * src/test/resources, rather than the full forecast pipeline.
 */
class PythonForecastRunnerTest {

    private static final ForecastRequest REQUEST = new ForecastRequest(
            new ForecastRequest.RegionSpec("named", "california"),
            "2024-08-15T10:00:00Z");

    private static String fixture(String name) {
        return Path.of("src", "test", "resources", name).toString();
    }

    private static PythonForecastRunner runner(String script, long timeoutSeconds) {
        return new PythonForecastRunner(new ObjectMapper(), "python", fixture(script), ".", timeoutSeconds);
    }

    @Test
    void returnsSuccessForAWellBehavedScript() {
        ForecastOutcome outcome = runner("well_behaved_forecast_stub.py", 30).run(REQUEST);

        assertTrue(outcome.success());
        assertFalse(outcome.transientFailure());
        assertEquals(Map.of("ok", true, "cutoff", "2024-08-15T10:00:00Z"), outcome.result());
    }

    @Test
    void returnsPermanentFailureForANonZeroExit() {
        ForecastOutcome outcome = runner("failing_forecast_stub.py", 30).run(REQUEST);

        assertFalse(outcome.success());
        assertFalse(outcome.transientFailure(), "a request-specific failure must not be retried");
        assertEquals("synthetic failure", outcome.error());
    }

    @Test
    void returnsTransientFailureAndKillsTheProcessOnTimeout() {
        PythonForecastRunner runner = runner("slow_forecast_stub.py", 1);

        Instant start = Instant.now();
        ForecastOutcome outcome = runner.run(REQUEST);
        Duration elapsed = Duration.between(start, Instant.now());

        assertFalse(outcome.success());
        assertTrue(outcome.transientFailure(), "a timeout must be retryable");
        assertTrue(elapsed.getSeconds() < 15, "the process should be killed near the timeout, not run to completion");
    }

    @Test
    void returnsTransientFailureWhenTheExecutableCannotBeStarted() {
        PythonForecastRunner runner = new PythonForecastRunner(
                new ObjectMapper(),
                "does-not-exist-" + System.nanoTime(),
                fixture("well_behaved_forecast_stub.py"),
                ".",
                30);

        ForecastOutcome outcome = runner.run(REQUEST);

        assertFalse(outcome.success());
        assertTrue(outcome.transientFailure(), "an unavailable interpreter is a dependency problem, not a request problem");
    }
}
