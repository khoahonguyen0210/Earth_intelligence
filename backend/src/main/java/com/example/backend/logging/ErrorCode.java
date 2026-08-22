package com.example.backend.logging;

/**
 * Task 13.1: stable, machine-readable failure codes for the structured
 * logs' `error_code` field. The human-readable error text still goes to
 * the API response and the database unchanged; these exist so a log
 * query can count or alert on a failure *kind* without pattern-matching
 * free text that embeds paths, exit codes, or Python messages.
 *
 * Named after where the failure happened in the Python subprocess
 * bridge (PythonForecastRunner/PythonAnalysisRunner), the only place
 * either pipeline can currently fail.
 */
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
    OUTPUT_READ_FAILED
}
