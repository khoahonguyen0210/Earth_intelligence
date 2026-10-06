package com.example.backend.forecast;

import com.example.backend.logging.ErrorCode;
import com.example.backend.tracing.Spans;
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

@Service
public class PythonForecastRunner implements ForecastRunner {

    private final ObjectMapper objectMapper;
    private final String pythonExecutable;
    private final String scriptPath;
    private final String workingDirectory;
    private final long timeoutSeconds;
    private final Spans spans;
    private final ExecutorService ioExecutor = Executors.newFixedThreadPool(2, PythonForecastRunner::newDaemonThread);

    public PythonForecastRunner(
            ObjectMapper objectMapper,
            @Value("${forecast.python.executable}") String pythonExecutable,
            @Value("${forecast.python.script-path}") String scriptPath,
            @Value("${forecast.python.working-directory}") String workingDirectory,
            @Value("${forecast.python.timeout-seconds}") long timeoutSeconds,
            Spans spans) {
        this.objectMapper = objectMapper;
        this.pythonExecutable = pythonExecutable;
        this.scriptPath = scriptPath;
        this.workingDirectory = workingDirectory;
        this.timeoutSeconds = timeoutSeconds;
        this.spans = spans;
    }

    @Override
    public ForecastOutcome run(ForecastRequest request) {
        return spans.child("forecast.python", () -> {
            ForecastOutcome outcome = runProcess(request);
            outcome.timingsMs().forEach((stage, millis) -> spans.tag("python." + stage + "_ms", millis));
            if (!outcome.success()) {
                spans.tag("error.code", outcome.errorCode());
                spans.fail(outcome.errorCode().name());
            }
            return outcome;
        });
    }

    private ForecastOutcome runProcess(ForecastRequest request) {
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
