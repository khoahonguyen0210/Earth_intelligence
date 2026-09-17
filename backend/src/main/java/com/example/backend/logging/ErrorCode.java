package com.example.backend.logging;

public enum ErrorCode {
    /** The Python process could not be started or written to (IOException). */
    PYTHON_START_FAILED,
    /** The Python process exceeded forecast.python.timeout-seconds and was killed. */
    PYTHON_TIMEOUT,
    /** The waiting thread was interrupted before the process finished. */
    PYTHON_INTERRUPTED,
    /** The script exited non-zero -- it rejected the request or its data. */
    PYTHON_FAILED,
    /** The script exited 0 but stdout was not the expected JSON. */
    OUTPUT_PARSE_FAILED,
    /** stdout/stderr could not be read back from the process. */
    OUTPUT_READ_FAILED,
    WORKER_LOST
}
