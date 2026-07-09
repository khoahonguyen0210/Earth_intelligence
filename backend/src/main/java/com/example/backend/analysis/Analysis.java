package com.example.backend.analysis;

import java.time.Instant;

public record Analysis(
        String id,
        AnalysisRequest request,
        Instant createdAt,
        Status status,
        Object result,
        Object evidence,
        String error) {

    public enum Status {
        SUCCEEDED,
        FAILED
    }

    public static Analysis from(String id, AnalysisRequest request, Instant createdAt, AnalysisOutcome outcome) {
        return new Analysis(
                id,
                request,
                createdAt,
                outcome.success() ? Status.SUCCEEDED : Status.FAILED,
                outcome.result(),
                outcome.evidence(),
                outcome.error());
    }
}
