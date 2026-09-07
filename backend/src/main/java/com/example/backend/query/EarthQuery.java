package com.example.backend.query;

import java.time.Instant;

public record EarthQuery(
        String id,
        EarthQueryRequest request,
        Instant createdAt,
        Status status,
        Object result,
        String error) {

    public enum Status {
        SUCCEEDED,
        FAILED
    }

    public static EarthQuery from(String id, EarthQueryRequest request, Instant createdAt, EarthQueryOutcome outcome) {
        return new EarthQuery(
                id,
                request,
                createdAt,
                outcome.success() ? Status.SUCCEEDED : Status.FAILED,
                outcome.result(),
                outcome.error());
    }
}
