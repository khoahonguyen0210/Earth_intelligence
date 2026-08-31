package com.example.backend.analysis;

import com.example.backend.logging.SecretRedactor;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import jakarta.validation.Valid;
import java.net.URI;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AnalysisController {

    public record AnalysisSummaryResponse(String id, String status) {
    }

    public record ResultResponse(String id, Object result, Object evidence) {
    }

    public record ErrorResponse(String error) {
    }

    private static final Logger log = LoggerFactory.getLogger(AnalysisController.class);

    private final AnalysisRunner runner;
    private final AnalysisStore store;
    private final SecretRedactor redactor;
    private final MeterRegistry meterRegistry;

    public AnalysisController(
            AnalysisRunner runner, AnalysisStore store, SecretRedactor redactor, MeterRegistry meterRegistry) {
        this.runner = runner;
        this.store = store;
        this.redactor = redactor;
        this.meterRegistry = meterRegistry;
    }

    @PostMapping("/analyses")
    public ResponseEntity<AnalysisSummaryResponse> createAnalysis(@Valid @RequestBody AnalysisRequest request) {
        String id = UUID.randomUUID().toString();
        long startNanos = System.nanoTime();
        // Task 13.4: redacted before it is stored, returned or logged.
        AnalysisOutcome outcome = runner.run(request).redacted(redactor);
        long durationNanos = System.nanoTime() - startNanos;
        long durationMs = durationNanos / 1_000_000;
        Analysis analysis = Analysis.from(id, request, Instant.now(), outcome);

        // Task 13.2: tagged by outcome and error code only -- never by the
        // request's own operation/region text, which a client controls.
        Timer.builder("analysis.duration")
                .description("Wall-clock time of one Earth analysis, including the Python subprocess")
                .tag("outcome", outcome.success() ? "succeeded" : "failed")
                .tag("error_code", outcome.errorCode() == null ? "none" : outcome.errorCode().name())
                .register(meterRegistry)
                .record(durationNanos, TimeUnit.NANOSECONDS);

        store.save(analysis);

        // Analysis runs synchronously on the request thread (no queue), so
        // its line shares the request's request_id directly.
        if (outcome.success()) {
            log.atInfo()
                    .addKeyValue("event", "analysis_succeeded")
                    .addKeyValue("analysis_id", id)
                    .addKeyValue("operation", request.operation())
                    .addKeyValue("duration_ms", durationMs)
                    .log("analysis succeeded");
        } else {
            log.atWarn()
                    .addKeyValue("event", "analysis_failed")
                    .addKeyValue("analysis_id", id)
                    .addKeyValue("operation", request.operation())
                    .addKeyValue("duration_ms", durationMs)
                    .addKeyValue("error_code", outcome.errorCode())
                    .log("analysis failed: {}", outcome.error());
        }

        return ResponseEntity.created(URI.create("/analyses/" + id))
                .body(new AnalysisSummaryResponse(analysis.id(), analysis.status().name()));
    }

    @GetMapping("/analyses/{id}")
    public ResponseEntity<AnalysisSummaryResponse> getAnalysis(@PathVariable String id) {
        return store.find(id)
                .map(analysis -> ResponseEntity.ok(new AnalysisSummaryResponse(analysis.id(), analysis.status().name())))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping("/results/{id}")
    public ResponseEntity<?> getResult(@PathVariable String id) {
        return store.find(id)
                .<ResponseEntity<?>>map(analysis -> {
                    if (analysis.status() == Analysis.Status.FAILED) {
                        return ResponseEntity.status(422).body(new ErrorResponse(analysis.error()));
                    }

                    return ResponseEntity.ok(new ResultResponse(analysis.id(), analysis.result(), analysis.evidence()));
                })
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
