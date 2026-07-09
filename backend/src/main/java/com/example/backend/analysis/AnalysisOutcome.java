package com.example.backend.analysis;

public record AnalysisOutcome(boolean success, Object result, Object evidence, String error) {

    public static AnalysisOutcome success(Object result, Object evidence) {
        return new AnalysisOutcome(true, result, evidence, null);
    }

    public static AnalysisOutcome failure(String error) {
        return new AnalysisOutcome(false, null, null, error);
    }
}
