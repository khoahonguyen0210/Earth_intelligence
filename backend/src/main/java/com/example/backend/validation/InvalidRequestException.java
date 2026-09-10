package com.example.backend.validation;

/** A request the API rejects before doing any work -- answered 400 by ApiErrorHandler. */
public class InvalidRequestException extends RuntimeException {

    public InvalidRequestException(String message) {
        super(message);
    }
}
