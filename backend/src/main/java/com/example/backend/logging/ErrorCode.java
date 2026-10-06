package com.example.backend.logging;

public enum ErrorCode {
    PYTHON_START_FAILED,
    PYTHON_TIMEOUT,
    PYTHON_INTERRUPTED,
    PYTHON_FAILED,
    OUTPUT_PARSE_FAILED,
    OUTPUT_READ_FAILED,
    WORKER_LOST
}
