package com.example.backend.query;

import com.example.backend.logging.ErrorCode;
import com.example.backend.logging.SecretRedactor;

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
