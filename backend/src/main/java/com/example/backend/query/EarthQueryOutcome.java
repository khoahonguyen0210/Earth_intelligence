package com.example.backend.query;

import com.example.backend.logging.ErrorCode;
import com.example.backend.logging.SecretRedactor;

/**
 * Mirrors AnalysisOutcome exactly (a stable ErrorCode for structured
 * logs, never persisted or returned; the same error-text redaction).
 * `result` is
 * the whole JSON object run_ask_earth.py returns -- answer, facts,
 * outputs, plan (docs/ask-earth.md) -- stored as one JSON blob, the same
 * way Forecast.result already is.
 */
public record EarthQueryOutcome(boolean success, Object result, String error, ErrorCode errorCode) {

    public static EarthQueryOutcome success(Object result) {
        return new EarthQueryOutcome(true, result, null, null);
    }

    public static EarthQueryOutcome failure(ErrorCode errorCode, String error) {
        return new EarthQueryOutcome(false, null, error, errorCode);
    }

    public EarthQueryOutcome redacted(SecretRedactor redactor) {
        return error == null ? this : new EarthQueryOutcome(success, result, redactor.redact(error), errorCode);
    }
}
