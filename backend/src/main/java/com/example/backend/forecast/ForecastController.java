package com.example.backend.forecast;

import jakarta.validation.Valid;
import java.net.URI;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
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

    private final ForecastQueue queue;
    private final ForecastStore store;

    public ForecastController(ForecastQueue queue, ForecastStore store) {
        this.queue = queue;
        this.store = store;
    }

    @PostMapping("/forecasts")
    public ResponseEntity<ForecastSummaryResponse> createForecast(
            @Valid @RequestBody ForecastRequest request,
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey) {
        String key = (idempotencyKey == null || idempotencyKey.isBlank()) ? null : idempotencyKey;

        if (key != null) {
            Optional<Forecast> existing = store.findByIdempotencyKey(key);
            if (existing.isPresent()) {
                return existingForecastResponse(existing.get());
            }
        }

        String id = UUID.randomUUID().toString();
        Forecast forecast = Forecast.pending(id, request, Instant.now(), key);

        try {
            store.save(forecast);
        } catch (DataIntegrityViolationException e) {
            // Lost a race against a concurrent request carrying the same
            // idempotency key (Task 6.6: "same idempotency key -> one
            // logical job") -- the other request's row won; return it.
            return store.findByIdempotencyKey(key)
                    .map(this::existingForecastResponse)
                    .orElseThrow(() -> e);
        }

        queue.enqueue(id);

        return ResponseEntity.created(URI.create("/forecasts/" + id))
                .body(new ForecastSummaryResponse(forecast.id(), forecast.status().name()));
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
