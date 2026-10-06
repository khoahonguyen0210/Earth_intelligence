package com.example.backend.forecast;

import com.example.backend.logging.ErrorCode;
import com.example.backend.logging.SecretRedactor;
import java.util.Map;

public record ForecastOutcome(
        boolean success,
        Object result,
        String error,
        boolean transientFailure,
        ErrorCode errorCode,
        Map<String, Double> timingsMs) {

    public static ForecastOutcome success(Object result) {
        return success(result, Map.of());
    }

    public static ForecastOutcome success(Object result, Map<String, Double> timingsMs) {
        return new ForecastOutcome(true, result, null, false, null, Map.copyOf(timingsMs));
    }

    public static ForecastOutcome failure(ErrorCode errorCode, String error) {
        return new ForecastOutcome(false, null, error, false, errorCode, Map.of());
    }

    public static ForecastOutcome transientFailure(ErrorCode errorCode, String error) {
        return new ForecastOutcome(false, null, error, true, errorCode, Map.of());
    }

    public ForecastOutcome redacted(SecretRedactor redactor) {
        return error == null
                ? this
                : new ForecastOutcome(success, result, redactor.redact(error), transientFailure, errorCode, timingsMs);
    }
}
