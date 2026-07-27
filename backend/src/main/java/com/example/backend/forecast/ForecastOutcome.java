package com.example.backend.forecast;

/**
 * Unlike AnalysisOutcome, there is no separate evidence slot here: per
 * docs/forecast-api-contract.md, evidence is nested inside result itself
 * (the Python side's forecast_result_to_dict already embeds it), not a
 * sibling field.
 */
public record ForecastOutcome(boolean success, Object result, String error) {

    public static ForecastOutcome success(Object result) {
        return new ForecastOutcome(true, result, null);
    }

    public static ForecastOutcome failure(String error) {
        return new ForecastOutcome(false, null, error);
    }
}
