package com.example.backend.query;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.backend.logging.ErrorCode;
import com.example.backend.tracing.Spans;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

/**
 * Mirrors PythonForecastRunnerTest exactly: the real python interpreter
 * and tiny fixture scripts under src/test/resources, not the full Ask
 * Earth pipeline (that is run_ask_earth.py's own tests, in ml/).
 */
class PythonEarthQueryRunnerTest {

    private static final EarthQueryRequest REQUEST =
            new EarthQueryRequest("How many fires occurred in California?");

    private static String fixture(String name) {
        return Path.of("src", "test", "resources", name).toString();
    }

    private static ServerPort serverPort(int port) {
        ServerPort serverPort = new ServerPort();
        serverPort.setForTest(port);
        return serverPort;
    }

    private static PythonEarthQueryRunner runner(String script, long timeoutSeconds, int port) {
        return new PythonEarthQueryRunner(
                new ObjectMapper(), "python", fixture(script), ".", timeoutSeconds, serverPort(port), Spans.noop());
    }

    @Test
    void returnsSuccessForAWellBehavedScript() {
        EarthQueryOutcome outcome = runner("well_behaved_ask_earth_stub.py", 30, 8080).run(REQUEST);

        assertTrue(outcome.success());
        @SuppressWarnings("unchecked")
        var result = (java.util.Map<String, Object>) outcome.result();
        assertEquals("There were 3 fires (computed).", result.get("answer"));
    }

    @Test
    void setsTheBackendBaseUrlFromTheRealBoundServerPort() {
        EarthQueryOutcome outcome = runner("well_behaved_ask_earth_stub.py", 30, 51234).run(REQUEST);

        @SuppressWarnings("unchecked")
        var result = (java.util.Map<String, Object>) outcome.result();
        assertEquals("http://localhost:51234", result.get("backend_base_url_seen"));
    }

    @Test
    void returnsFailureForANonZeroExit() {
        EarthQueryOutcome outcome = runner("failing_ask_earth_stub.py", 30, 8080).run(REQUEST);

        assertFalse(outcome.success());
        assertEquals("the planner refused to answer: synthetic safety block", outcome.error());
        assertEquals(ErrorCode.PYTHON_FAILED, outcome.errorCode());
    }

    @Test
    void killsAndReportsATimeoutRatherThanHanging() {
        PythonEarthQueryRunner runner = runner("slow_ask_earth_stub.py", 1, 8080);

        Instant start = Instant.now();
        EarthQueryOutcome outcome = runner.run(REQUEST);
        Duration elapsed = Duration.between(start, Instant.now());

        assertFalse(outcome.success());
        assertEquals(ErrorCode.PYTHON_TIMEOUT, outcome.errorCode());
        assertTrue(elapsed.getSeconds() < 15, "the process should be killed near the timeout, not run to completion");
    }

    @Test
    void returnsAStartFailureWhenTheInterpreterCannotBeFound() {
        PythonEarthQueryRunner runner = new PythonEarthQueryRunner(
                new ObjectMapper(),
                "does-not-exist-" + System.nanoTime(),
                fixture("well_behaved_ask_earth_stub.py"),
                ".",
                30,
                serverPort(8080),
                Spans.noop());

        EarthQueryOutcome outcome = runner.run(REQUEST);

        assertFalse(outcome.success());
        assertEquals(ErrorCode.PYTHON_START_FAILED, outcome.errorCode());
    }
}
