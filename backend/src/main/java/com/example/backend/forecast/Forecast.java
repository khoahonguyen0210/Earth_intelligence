package com.example.backend.forecast;

import java.time.Instant;

public record Forecast(
        String id,
        ForecastRequest request,
        Instant createdAt,
        Status status,
        Object result,
        String error) {

    /**
     * Only SUCCEEDED/FAILED are reachable while Task 6.2's synchronous
     * subprocess bridge is in place. PENDING/RUNNING/RETRYING/CANCELLED
     * are owned by Task 6.5's async worker/queue (see
     * docs/forecast-api-contract.md).
     */
    public enum Status {
        SUCCEEDED,
        FAILED
    }

    public static Forecast from(String id, ForecastRequest request, Instant createdAt, ForecastOutcome outcome) {
        return new Forecast(
                id,
                request,
                createdAt,
                outcome.success() ? Status.SUCCEEDED : Status.FAILED,
                outcome.result(),
                outcome.error());
    }
}
