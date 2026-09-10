package com.example.backend.analysis;

import com.example.backend.logging.ErrorCode;
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
 * Bridges to the Python analysis pipeline with a synchronous subprocess
 * call per request. This is deliberately simple: unlike forecasts,
 * analysis runs synchronously on the request thread rather than through
 * a queue and worker.
 */
@Service
public class PythonAnalysisRunner implements AnalysisRunner {

    private final ObjectMapper objectMapper;
    private final String pythonExecutable;
    private final String scriptPath;
    private final String workingDirectory;

    public PythonAnalysisRunner(
            ObjectMapper objectMapper,
            @Value("${analysis.python.executable}") String pythonExecutable,
            @Value("${analysis.python.script-path}") String scriptPath,
            @Value("${analysis.python.working-directory}") String workingDirectory) {
        this.objectMapper = objectMapper;
        this.pythonExecutable = pythonExecutable;
        this.scriptPath = scriptPath;
        this.workingDirectory = workingDirectory;
    }

    @Override
    public AnalysisOutcome run(AnalysisRequest request) {
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
                return AnalysisOutcome.failure(ErrorCode.PYTHON_FAILED, extractErrorMessage(stdout, stderr, exitCode));
            }

            Map<String, Object> payload = objectMapper.readValue(stdout, new TypeReference<>() {
            });

            return AnalysisOutcome.success(payload.get("result"), payload.get("evidence"));
        } catch (IOException e) {
            return AnalysisOutcome.failure(ErrorCode.PYTHON_START_FAILED, "Failed to run Python analysis: " + e.getMessage());
        } catch (JacksonException e) {
            return AnalysisOutcome.failure(ErrorCode.OUTPUT_PARSE_FAILED, "Failed to parse Python analysis output: " + e.getMessage());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return AnalysisOutcome.failure(ErrorCode.PYTHON_INTERRUPTED, "Python analysis was interrupted: " + e.getMessage());
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

        return "Python analysis process failed (exit " + exitCode + "): " + stderr;
    }

    private String readAll(java.io.InputStream stream) throws IOException {
        return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
    }
}
