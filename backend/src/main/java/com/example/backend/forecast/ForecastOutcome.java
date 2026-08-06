package com.example.backend.forecast;

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
 */
public record ForecastOutcome(boolean success, Object result, String error, boolean transientFailure) {

    public static ForecastOutcome success(Object result) {
        return new ForecastOutcome(true, result, null, false);
    }

    public static ForecastOutcome failure(String error) {
        return new ForecastOutcome(false, null, error, false);
    }

    public static ForecastOutcome transientFailure(String error) {
        return new ForecastOutcome(false, null, error, true);
    }
}
