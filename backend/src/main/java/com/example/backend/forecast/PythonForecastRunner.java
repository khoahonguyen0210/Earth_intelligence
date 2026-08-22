package com.example.backend.forecast;

import com.example.backend.logging.ErrorCode;
import jakarta.annotation.PreDestroy;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import tools.jackson.core.JacksonException;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * Task 6.2 bridge to the Python forecast pipeline: a synchronous
 * subprocess call per job, the same interim pattern PythonAnalysisRunner
 * already uses for analysis. Task 6.5 moved the caller off the request
 * thread into ForecastWorker; Task 6.6 added the timeout/classification
 * below (see docs/forecast-retry-and-idempotency.md).
 *
 * stdout/stderr are drained on background threads while the main thread
 * waits on the process with a timeout, rather than reading them
 * sequentially after waiting: a process whose combined output exceeds
 * the OS pipe buffer will block on its own write call until something
 * reads, so waiting for exit before reading would deadlock on any
 * sufficiently large forecast payload (a full California grid
 * FeatureCollection easily can be).
 */
@Service
public class PythonForecastRunner implements ForecastRunner {

    private final ObjectMapper objectMapper;
    private final String pythonExecutable;
    private final String scriptPath;
    private final String workingDirectory;
    private final long timeoutSeconds;
    private final ExecutorService ioExecutor = Executors.newFixedThreadPool(2, PythonForecastRunner::newDaemonThread);

    public PythonForecastRunner(
            ObjectMapper objectMapper,
            @Value("${forecast.python.executable}") String pythonExecutable,
            @Value("${forecast.python.script-path}") String scriptPath,
            @Value("${forecast.python.working-directory}") String workingDirectory,
            @Value("${forecast.python.timeout-seconds}") long timeoutSeconds) {
        this.objectMapper = objectMapper;
        this.pythonExecutable = pythonExecutable;
        this.scriptPath = scriptPath;
        this.workingDirectory = workingDirectory;
        this.timeoutSeconds = timeoutSeconds;
    }

    @Override
    public ForecastOutcome run(ForecastRequest request) {
        try {
            ProcessBuilder builder = new ProcessBuilder(pythonExecutable, scriptPath);
            builder.directory(new File(workingDirectory));

            Process process = builder.start();

            try (var stdin = process.getOutputStream()) {
                stdin.write(objectMapper.writeValueAsBytes(request));
            }

            Future<String> stdoutFuture = ioExecutor.submit(() -> readAll(process.getInputStream()));
            Future<String> stderrFuture = ioExecutor.submit(() -> readAll(process.getErrorStream()));

            if (!process.waitFor(timeoutSeconds, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                stdoutFuture.cancel(true);
                stderrFuture.cancel(true);
                return ForecastOutcome.transientFailure(ErrorCode.PYTHON_TIMEOUT,
                        "Python forecast timed out after " + timeoutSeconds + "s and was terminated");
            }

            String stdout = stdoutFuture.get();
            String stderr = stderrFuture.get();
            int exitCode = process.exitValue();

            if (exitCode != 0) {
                return ForecastOutcome.failure(ErrorCode.PYTHON_FAILED, extractErrorMessage(stdout, stderr, exitCode));
            }

            Map<String, Object> payload = objectMapper.readValue(stdout, new TypeReference<>() {
            });

            return ForecastOutcome.success(payload.get("result"), timings(payload.get("timings_ms")));
        } catch (IOException e) {
            // Couldn't even start/write to the process -- a dependency
            // problem (missing interpreter, exhausted resources), not
            // something about this particular request.
            return ForecastOutcome.transientFailure(ErrorCode.PYTHON_START_FAILED, "Failed to run Python forecast: " + e.getMessage());
        } catch (JacksonException e) {
            return ForecastOutcome.failure(ErrorCode.OUTPUT_PARSE_FAILED, "Failed to parse Python forecast output: " + e.getMessage());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return ForecastOutcome.transientFailure(ErrorCode.PYTHON_INTERRUPTED, "Python forecast was interrupted: " + e.getMessage());
        } catch (ExecutionException e) {
            return ForecastOutcome.failure(ErrorCode.OUTPUT_READ_FAILED, "Failed to read Python forecast output: " + e.getCause());
        }
    }

    /**
     * Task 13.2: the Python side's optional `timings_ms` object
     * (query/run_forecast.py). Anything missing or non-numeric is
     * dropped rather than failing a forecast that otherwise succeeded --
     * timings are observability, not part of the result.
     */
    private static Map<String, Double> timings(Object raw) {
        if (!(raw instanceof Map<?, ?> entries)) {
            return Map.of();
        }

        Map<String, Double> timings = new HashMap<>();
        entries.forEach((key, value) -> {
            if (key instanceof String stage && value instanceof Number millis) {
                timings.put(stage, millis.doubleValue());
            }
        });
        return timings;
    }

    private String extractErrorMessage(String stdout, String stderr, int exitCode) {
        try {
            Map<String, Object> errorPayload = objectMapper.readValue(stdout, new TypeReference<Map<String, Object>>() {
            });
            Object message = errorPayload.get("error");

            if (message != null) {
                return message.toString();
            }
        } catch (JacksonException ignored) {
            // stdout wasn't valid JSON; fall through to the raw message below.
        }

        return "Python forecast process failed (exit " + exitCode + "): " + stderr;
    }

    private String readAll(java.io.InputStream stream) throws IOException {
        return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
    }

    private static Thread newDaemonThread(Runnable task) {
        Thread thread = new Thread(task, "python-forecast-runner-io");
        thread.setDaemon(true);
        return thread;
    }

    @PreDestroy
    void shutdown() {
        ioExecutor.shutdownNow();
    }
}
