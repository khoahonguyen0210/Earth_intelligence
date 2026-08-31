package com.example.backend.analysis;

import com.example.backend.logging.ErrorCode;
import com.example.backend.logging.SecretRedactor;

/**
 * Task 13.1: a failure carries a stable ErrorCode for the structured
 * logs; like ForecastOutcome's, it is not persisted or returned by the API.
 */
public record AnalysisOutcome(boolean success, Object result, Object evidence, String error, ErrorCode errorCode) {

    public static AnalysisOutcome success(Object result, Object evidence) {
        return new AnalysisOutcome(true, result, evidence, null, null);
    }

    public static AnalysisOutcome failure(ErrorCode errorCode, String error) {
        return new AnalysisOutcome(false, null, null, error, errorCode);
    }

    /** Task 13.4: see ForecastOutcome.redacted -- the error is stored and returned, not only logged. */
    public AnalysisOutcome redacted(SecretRedactor redactor) {
        return error == null ? this : new AnalysisOutcome(success, result, evidence, redactor.redact(error), errorCode);
    }
}
