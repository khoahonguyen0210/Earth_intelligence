package com.example.backend.forecast;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import tools.jackson.core.JacksonException;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * Task 6.2 bridge to the Python forecast pipeline: a synchronous
 * subprocess call per request, the same interim pattern
 * PythonAnalysisRunner already uses for analysis. The proper async
 * worker/queue architecture (Task 6.5, Redis-backed) replaces this once
 * it exists.
 */
@Service
public class PythonForecastRunner implements ForecastRunner {

    private final ObjectMapper objectMapper;
    private final String pythonExecutable;
    private final String scriptPath;
    private final String workingDirectory;

    public PythonForecastRunner(
            ObjectMapper objectMapper,
            @Value("${forecast.python.executable}") String pythonExecutable,
            @Value("${forecast.python.script-path}") String scriptPath,
            @Value("${forecast.python.working-directory}") String workingDirectory) {
        this.objectMapper = objectMapper;
        this.pythonExecutable = pythonExecutable;
        this.scriptPath = scriptPath;
        this.workingDirectory = workingDirectory;
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

            String stdout = readAll(process.getInputStream());
            String stderr = readAll(process.getErrorStream());

            int exitCode = process.waitFor();

            if (exitCode != 0) {
                return ForecastOutcome.failure(extractErrorMessage(stdout, stderr, exitCode));
            }

            Map<String, Object> payload = objectMapper.readValue(stdout, new TypeReference<>() {
            });

            return ForecastOutcome.success(payload.get("result"));
        } catch (IOException e) {
            return ForecastOutcome.failure("Failed to run Python forecast: " + e.getMessage());
        } catch (JacksonException e) {
            return ForecastOutcome.failure("Failed to parse Python forecast output: " + e.getMessage());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return ForecastOutcome.failure("Python forecast was interrupted: " + e.getMessage());
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

        return "Python forecast process failed (exit " + exitCode + "): " + stderr;
    }

    private String readAll(java.io.InputStream stream) throws IOException {
        return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
    }
}
