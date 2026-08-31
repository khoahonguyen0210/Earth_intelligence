package com.example.backend.validation;

/** Task 13.4: a request the API rejects before doing any work -- answered 400 by ApiErrorHandler. */
public class InvalidRequestException extends RuntimeException {

    public InvalidRequestException(String message) {
        super(message);
    }
}
