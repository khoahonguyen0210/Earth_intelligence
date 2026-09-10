package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.backend.logging.ErrorCode;
import com.example.backend.tracing.Spans;
import com.example.backend.tracing.TestTracing;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.sdk.trace.data.SpanData;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

/**
 * PythonForecastRunner's timeout/kill and transient-vs-permanent
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
        return new PythonForecastRunner(new ObjectMapper(), "python", fixture(script), ".", timeoutSeconds, Spans.noop());
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
        assertEquals(ErrorCode.PYTHON_FAILED, outcome.errorCode());
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
        assertEquals(ErrorCode.PYTHON_TIMEOUT, outcome.errorCode());
    }

    @Test
    void returnsTransientFailureWhenTheExecutableCannotBeStarted() {
        PythonForecastRunner runner = new PythonForecastRunner(
                new ObjectMapper(),
                "does-not-exist-" + System.nanoTime(),
                fixture("well_behaved_forecast_stub.py"),
                ".",
                30,
                Spans.noop());

        ForecastOutcome outcome = runner.run(REQUEST);

        assertFalse(outcome.success());
        assertTrue(outcome.transientFailure(), "an unavailable interpreter is a dependency problem, not a request problem");
        assertEquals(ErrorCode.PYTHON_START_FAILED, outcome.errorCode());
    }

    @Test
    void carriesThePipelinesNumericStageTimingsAndDropsMalformedOnes() {
        ForecastOutcome outcome = runner("timed_forecast_stub.py", 30).run(REQUEST);

        assertTrue(outcome.success());
        assertEquals(Map.of("ok", true), outcome.result(), "timings must not leak into the result");
        assertEquals(Map.of("data_load", 120.5, "model_fit", 800.0, "model_inference", 4.25, "total", 930.0),
                outcome.timingsMs());
    }

    @Test
    void aScriptThatReportsNoTimingsStillSucceedsWithNone() {
        ForecastOutcome outcome = runner("well_behaved_forecast_stub.py", 30).run(REQUEST);

        assertTrue(outcome.timingsMs().isEmpty());
    }

    @Test
    void aTracedRunIsAForecastPythonSpanCarryingThePipelinesStageTimings() {
        TestTracing tracing = new TestTracing();
        PythonForecastRunner runner = new PythonForecastRunner(
                new ObjectMapper(), "python", fixture("timed_forecast_stub.py"), ".", 30, tracing.spans());

        tracing.spans().root("forecast.job.attempt", () -> runner.run(REQUEST));

        SpanData python = tracing.only("forecast.python");
        assertEquals(tracing.only("forecast.job.attempt").getSpanId(), python.getParentSpanId());
        assertEquals(4.25, python.getAttributes().get(AttributeKey.doubleKey("python.model_inference_ms")));
        assertEquals(120.5, python.getAttributes().get(AttributeKey.doubleKey("python.data_load_ms")));
        assertNotEquals(StatusCode.ERROR, python.getStatus().getStatusCode());
    }

    @Test
    void aFailedTracedRunMarksItsSpanWithTheErrorCodeOnly() {
        TestTracing tracing = new TestTracing();
        PythonForecastRunner runner = new PythonForecastRunner(
                new ObjectMapper(), "python", fixture("failing_forecast_stub.py"), ".", 30, tracing.spans());

        tracing.spans().root("forecast.job.attempt", () -> runner.run(REQUEST));

        SpanData python = tracing.only("forecast.python");
        assertEquals(StatusCode.ERROR, python.getStatus().getStatusCode());
        assertEquals("PYTHON_FAILED", python.getStatus().getDescription(),
                "unredacted Python text stays off the span; the worker's span gets the redacted text");
        assertEquals("PYTHON_FAILED", python.getAttributes().get(AttributeKey.stringKey("error.code")));
        assertFalse(tracing.finished().toString().contains("synthetic failure"), "unredacted Python text");
    }
}
