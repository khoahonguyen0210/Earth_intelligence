package com.example.backend.query;

import com.example.backend.logging.ErrorCode;
import com.example.backend.tracing.Spans;
import jakarta.annotation.PreDestroy;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
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
public class PythonEarthQueryRunner implements EarthQueryRunner {

    private final ObjectMapper objectMapper;
    private final String pythonExecutable;
    private final String scriptPath;
    private final String workingDirectory;
    private final long timeoutSeconds;
    private final ServerPort serverPort;
    private final Spans spans;
    private final ExecutorService ioExecutor = Executors.newFixedThreadPool(2, PythonEarthQueryRunner::newDaemonThread);

    public PythonEarthQueryRunner(
            ObjectMapper objectMapper,
            @Value("${ask-earth.python.executable}") String pythonExecutable,
            @Value("${ask-earth.python.script-path}") String scriptPath,
            @Value("${ask-earth.python.working-directory}") String workingDirectory,
            @Value("${ask-earth.python.timeout-seconds}") long timeoutSeconds,
            ServerPort serverPort,
            Spans spans) {
        this.objectMapper = objectMapper;
        this.pythonExecutable = pythonExecutable;
        this.scriptPath = scriptPath;
        this.workingDirectory = workingDirectory;
        this.timeoutSeconds = timeoutSeconds;
        this.serverPort = serverPort;
        this.spans = spans;
    }

    @Override
    public EarthQueryOutcome run(EarthQueryRequest request) {
        return spans.child("earth_query.python", () -> runProcess(request));
    }

    private EarthQueryOutcome runProcess(EarthQueryRequest request) {
        try {
            ProcessBuilder builder = new ProcessBuilder(pythonExecutable, scriptPath);
            builder.directory(new File(workingDirectory));
            builder.environment().put("ASK_EARTH_BACKEND_BASE_URL", "http://localhost:" + serverPort.get());

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
                return EarthQueryOutcome.failure(ErrorCode.PYTHON_TIMEOUT,
                        "Ask Earth query timed out after " + timeoutSeconds + "s and was terminated");
            }

            String stdout = stdoutFuture.get();
            String stderr = stderrFuture.get();
            int exitCode = process.exitValue();

            if (exitCode != 0) {
                return EarthQueryOutcome.failure(ErrorCode.PYTHON_FAILED, extractErrorMessage(stdout, stderr, exitCode));
            }

            Object result = objectMapper.readValue(stdout, new TypeReference<Map<String, Object>>() {
            });

            return EarthQueryOutcome.success(result);
        } catch (IOException e) {
            return EarthQueryOutcome.failure(ErrorCode.PYTHON_START_FAILED, "Failed to run Ask Earth query: " + e.getMessage());
        } catch (JacksonException e) {
            return EarthQueryOutcome.failure(ErrorCode.OUTPUT_PARSE_FAILED, "Failed to parse Ask Earth output: " + e.getMessage());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return EarthQueryOutcome.failure(ErrorCode.PYTHON_INTERRUPTED, "Ask Earth query was interrupted: " + e.getMessage());
        } catch (ExecutionException e) {
            return EarthQueryOutcome.failure(ErrorCode.OUTPUT_READ_FAILED, "Failed to read Ask Earth output: " + e.getCause());
        }
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

        return "Ask Earth query process failed (exit " + exitCode + "): " + stderr;
    }

    private String readAll(java.io.InputStream stream) throws IOException {
        return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
    }

    private static Thread newDaemonThread(Runnable task) {
        Thread thread = new Thread(task, "python-ask-earth-runner-io");
        thread.setDaemon(true);
        return thread;
    }

    @PreDestroy
    void shutdown() {
        ioExecutor.shutdownNow();
    }
}
