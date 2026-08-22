package com.example.backend.forecast;

import com.example.backend.logging.ErrorCode;
import java.util.Map;

/**
 * Unlike AnalysisOutcome, there is no separate evidence slot here: per
 * docs/forecast-api-contract.md, evidence is nested inside result itself
 * (the Python side's forecast_result_to_dict already embeds it), not a
 * sibling field.
 *
 * Task 6.6: a failure additionally says whether it is transient -- a
 * dependency problem (couldn't start the Python process, it timed out)
 * that a retry might resolve -- versus permanent -- a problem with this
 * particular request/data that retrying would only reproduce. Only
 * ForecastWorker acts on the distinction (see docs/forecast-retry-and-idempotency.md);
 * a successful outcome is never transient.
 *
 * Task 13.1: a failure also carries a stable ErrorCode for the
 * structured logs. It is not persisted or returned by the API -- the
 * human-readable error text still is, unchanged.
 *
 * Task 13.2: a success may carry the Python pipeline's own per-stage
 * wall-clock timings (`timings_ms`: data_load, model_fit,
 * model_inference, total), which ForecastWorker records as metrics.
 * Like errorCode, they are never persisted or returned to API clients.
 */
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
}
