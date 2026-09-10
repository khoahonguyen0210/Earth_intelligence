package com.example.backend.forecast;

import com.example.backend.tracing.Spans;
import com.example.backend.validation.InvalidRequestException;
import jakarta.validation.Valid;
import java.net.URI;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ForecastController {

    public record ForecastSummaryResponse(String forecastId, String status) {
    }

    public record ForecastResultResponse(String forecastId, Object result) {
    }

    public record ErrorResponse(String error) {
    }

    private static final Logger log = LoggerFactory.getLogger(ForecastController.class);

    /**
     * The key is stored (forecasts.idempotency_key is VARCHAR(255)) and
     * compared, never logged; anything longer or not plain visible ASCII
     * is refused up front instead of failing in the database as a 500.
     */
    private static final Pattern ACCEPTABLE_IDEMPOTENCY_KEY = Pattern.compile("[\\x21-\\x7E]{1,255}");

    private final ForecastQueue queue;
    private final ForecastStore store;
    private final Spans spans;

    public ForecastController(ForecastQueue queue, ForecastStore store, Spans spans) {
        this.queue = queue;
        this.store = store;
        this.spans = spans;
    }

    @PostMapping("/forecasts")
    public ResponseEntity<ForecastSummaryResponse> createForecast(
            @Valid @RequestBody ForecastRequest request,
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey) {
        String key = (idempotencyKey == null || idempotencyKey.isBlank()) ? null : idempotencyKey;
        if (key != null && !ACCEPTABLE_IDEMPOTENCY_KEY.matcher(key).matches()) {
            throw new InvalidRequestException("Idempotency-Key must be 1-255 visible ASCII characters");
        }

        if (key != null) {
            Optional<Forecast> existing = store.findByIdempotencyKey(key);
            if (existing.isPresent()) {
                logDeduplicated(existing.get());
                return existingForecastResponse(existing.get());
            }
        }

        String id = UUID.randomUUID().toString();
        // The job's own span. Its traceparent is stored on the row, so
        // every later worker attempt continues this request's trace
        // (docs/tracing.md).
        return spans.child("forecast.job.submit", () -> {
            spans.tag("job.id", id);
            Forecast forecast = Forecast.pending(id, request, Instant.now(), key, spans.currentTraceParent());

            try {
                store.save(forecast);
            } catch (DataIntegrityViolationException e) {
                // Lost a race against a concurrent request carrying the same
                // idempotency key -- the invariant is one logical job per
                // key -- the other request's row won; return it.
                return store.findByIdempotencyKey(key)
                        .map(winner -> {
                            logDeduplicated(winner);
                            return existingForecastResponse(winner);
                        })
                        .orElseThrow(() -> e);
            }

            // The row is the durable record of the job; the queue entry is
            // only how a worker hears about it. If Redis is down, the job
            // is still accepted, and ForecastRecovery enqueues it once
            // Redis is back (docs/reliability-tests.md).
            try {
                queue.enqueue(id);
                // job_id links this request's log line (and its request_id) to
                // every later ForecastWorker line for the same job.
                log.atInfo()
                        .addKeyValue("event", "job_enqueued")
                        .addKeyValue(ForecastWorker.MDC_JOB_ID, id)
                        .addKeyValue("idempotency_key_present", key != null)
                        .log("forecast job enqueued");
            } catch (DataAccessException e) {
                log.atWarn()
                        .addKeyValue("event", "job_enqueue_deferred")
                        .addKeyValue(ForecastWorker.MDC_JOB_ID, id)
                        .log("queue unavailable; job kept PENDING for recovery to enqueue: {}",
                                e.getClass().getSimpleName());
            }

            return ResponseEntity.created(URI.create("/forecasts/" + id))
                    .body(new ForecastSummaryResponse(forecast.id(), forecast.status().name()));
        });
    }

    private void logDeduplicated(Forecast existing) {
        log.atInfo()
                .addKeyValue("event", "job_deduplicated")
                .addKeyValue(ForecastWorker.MDC_JOB_ID, existing.id())
                .addKeyValue("status", existing.status().name())
                .log("idempotency key matched an existing forecast; nothing enqueued");
    }

    private ResponseEntity<ForecastSummaryResponse> existingForecastResponse(Forecast forecast) {
        return ResponseEntity.ok(new ForecastSummaryResponse(forecast.id(), forecast.status().name()));
    }

    @GetMapping("/forecasts/{id}")
    public ResponseEntity<ForecastSummaryResponse> getForecast(@PathVariable String id) {
        return store.find(id)
                .map(forecast -> ResponseEntity.ok(new ForecastSummaryResponse(forecast.id(), forecast.status().name())))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping("/forecasts/{id}/result")
    public ResponseEntity<?> getForecastResult(@PathVariable String id) {
        return store.find(id)
                .<ResponseEntity<?>>map(forecast -> {
                    if (forecast.status() == Forecast.Status.SUCCEEDED) {
                        return ResponseEntity.ok(new ForecastResultResponse(forecast.id(), forecast.result()));
                    }

                    if (forecast.status() == Forecast.Status.FAILED) {
                        return ResponseEntity.status(422).body(new ErrorResponse(forecast.error()));
                    }

                    // PENDING/RUNNING/RETRYING/CANCELLED: the job hasn't
                    // reached a terminal state yet, so there is no result
                    // to serve -- see docs/forecast-async-jobs.md.
                    return ResponseEntity.status(409).body(new ErrorResponse(
                            "forecast " + forecast.id() + " has not finished (status: " + forecast.status() + ")"));
                })
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
