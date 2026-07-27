package com.example.backend.forecast;

import jakarta.validation.Valid;
import java.net.URI;
import java.time.Instant;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ForecastController {

    public record ForecastSummaryResponse(String forecastId, String status) {
    }

    public record ForecastResultResponse(String forecastId, Object result) {
    }

    public record ErrorResponse(String error) {
    }

    private final ForecastRunner runner;
    private final ForecastStore store;

    public ForecastController(ForecastRunner runner, ForecastStore store) {
        this.runner = runner;
        this.store = store;
    }

    @PostMapping("/forecasts")
    public ResponseEntity<ForecastSummaryResponse> createForecast(@Valid @RequestBody ForecastRequest request) {
        String id = UUID.randomUUID().toString();
        ForecastOutcome outcome = runner.run(request);
        Forecast forecast = Forecast.from(id, request, Instant.now(), outcome);

        store.save(forecast);

        return ResponseEntity.created(URI.create("/forecasts/" + id))
                .body(new ForecastSummaryResponse(forecast.id(), forecast.status().name()));
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
                    if (forecast.status() == Forecast.Status.FAILED) {
                        return ResponseEntity.status(422).body(new ErrorResponse(forecast.error()));
                    }

                    return ResponseEntity.ok(new ForecastResultResponse(forecast.id(), forecast.result()));
                })
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
