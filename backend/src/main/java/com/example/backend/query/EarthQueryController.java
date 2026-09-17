package com.example.backend.query;

import com.example.backend.logging.SecretRedactor;
import com.example.backend.region.RegionStore;
import com.example.backend.tracing.Spans;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import jakarta.validation.Valid;
import java.net.URI;
import java.time.Instant;
import java.util.List;
import java.util.Map;
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
public class EarthQueryController {

    public record EarthQuerySummaryResponse(String id, String status) {
    }

    public record ResultResponse(String id, Object result) {
    }

    public record ErrorResponse(String error) {
    }

    private static final Logger log = LoggerFactory.getLogger(EarthQueryController.class);

    private final EarthQueryRunner runner;
    private final EarthQueryStore store;
    private final SecretRedactor redactor;
    private final MeterRegistry meterRegistry;
    private final Spans spans;
    private final RegionStore regionStore;

    public EarthQueryController(
            EarthQueryRunner runner,
            EarthQueryStore store,
            SecretRedactor redactor,
            MeterRegistry meterRegistry,
            Spans spans,
            RegionStore regionStore) {
        this.runner = runner;
        this.store = store;
        this.redactor = redactor;
        this.meterRegistry = meterRegistry;
        this.spans = spans;
        this.regionStore = regionStore;
    }

    @PostMapping("/queries")
    public ResponseEntity<EarthQuerySummaryResponse> createQuery(@Valid @RequestBody EarthQueryRequest request) {
        String id = UUID.randomUUID().toString();

        return spans.child("earth_query.submit", () -> {
            spans.tag("earth_query.id", id);

            long startNanos = System.nanoTime();
            EarthQueryOutcome outcome = runner.run(request).redacted(redactor);
            long durationNanos = System.nanoTime() - startNanos;
            long durationMs = durationNanos / 1_000_000;
            EarthQuery query = EarthQuery.from(id, request, Instant.now(), outcome);

            // Tagged by outcome/error code only, never by the question
            // text itself, which a client controls.
            Timer.builder("earth_query.duration")
                    .description("Wall-clock time of one Ask Earth question, including the Python subprocess")
                    .tag("outcome", outcome.success() ? "succeeded" : "failed")
                    .tag("error_code", outcome.errorCode() == null ? "none" : outcome.errorCode().name())
                    .register(meterRegistry)
                    .record(durationNanos, TimeUnit.NANOSECONDS);

            store.save(query);

            if (outcome.success()) {
                recordRegions(outcome.result());
                log.atInfo()
                        .addKeyValue("event", "earth_query_succeeded")
                        .addKeyValue("earth_query_id", id)
                        .addKeyValue("duration_ms", durationMs)
                        .log("ask earth query succeeded");
            } else {
                spans.tag("error.code", outcome.errorCode());
                spans.fail(outcome.errorCode() + ": " + outcome.error());
                log.atWarn()
                        .addKeyValue("event", "earth_query_failed")
                        .addKeyValue("earth_query_id", id)
                        .addKeyValue("duration_ms", durationMs)
                        .addKeyValue("error_code", outcome.errorCode())
                        .log("ask earth query failed: {}", outcome.error());
            }

            return ResponseEntity.created(URI.create("/queries/" + id))
                    .body(new EarthQuerySummaryResponse(query.id(), query.status().name()));
        });
    }

    /** Each fact carries its own resolved region (query.evidence's shape); a question can touch more than one. */
    private void recordRegions(Object result) {
        if (result instanceof Map<?, ?> resultMap && resultMap.get("facts") instanceof List<?> facts) {
            for (Object fact : facts) {
                if (fact instanceof Map<?, ?> factMap) {
                    regionStore.recordFrom(factMap.get("evidence"));
                }
            }
        }
    }

    @GetMapping("/queries/{id}")
    public ResponseEntity<EarthQuerySummaryResponse> getQuery(@PathVariable String id) {
        return store.find(id)
                .map(query -> ResponseEntity.ok(new EarthQuerySummaryResponse(query.id(), query.status().name())))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping("/queries/{id}/result")
    public ResponseEntity<?> getResult(@PathVariable String id) {
        return store.find(id)
                .<ResponseEntity<?>>map(query -> {
                    if (query.status() == EarthQuery.Status.FAILED) {
                        return ResponseEntity.status(422).body(new ErrorResponse(query.error()));
                    }

                    return ResponseEntity.ok(new ResultResponse(query.id(), query.result()));
                })
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
