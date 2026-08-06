package com.example.backend.forecast;

import java.time.Instant;

public record Forecast(
        String id,
        ForecastRequest request,
        Instant createdAt,
        Status status,
        Object result,
        String error,
        int attempts,
        String idempotencyKey) {

    /**
     * CANCELLED completes the state space the Execution Handbook's Task
     * 6.5 lists, but is not reachable yet: there is no cancel endpoint
     * (docs/forecast-api-contract.md locks the three existing routes).
     * RETRYING is real as of Task 6.6 -- see
     * docs/forecast-retry-and-idempotency.md.
     */
    public enum Status {
        PENDING,
        RUNNING,
        SUCCEEDED,
        FAILED,
        RETRYING,
        CANCELLED
    }

    public static Forecast pending(String id, ForecastRequest request, Instant createdAt, String idempotencyKey) {
        return new Forecast(id, request, createdAt, Status.PENDING, null, null, 0, idempotencyKey);
    }

    public static Forecast pending(String id, ForecastRequest request, Instant createdAt) {
        return pending(id, request, createdAt, null);
    }

    public static Forecast from(String id, ForecastRequest request, Instant createdAt, ForecastOutcome outcome) {
        return pending(id, request, createdAt).withOutcome(outcome);
    }

    public Forecast withStatus(Status status) {
        return new Forecast(id, request, createdAt, status, result, error, attempts, idempotencyKey);
    }

    public Forecast withAttempts(int attempts) {
        return new Forecast(id, request, createdAt, status, result, error, attempts, idempotencyKey);
    }

    public Forecast withOutcome(ForecastOutcome outcome) {
        return new Forecast(
                id,
                request,
                createdAt,
                outcome.success() ? Status.SUCCEEDED : Status.FAILED,
                outcome.result(),
                outcome.error(),
                attempts,
                idempotencyKey);
    }
}
