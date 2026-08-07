package com.example.backend.workflow;

/**
 * Executes one WorkflowNode's real work and reports the outcome.
 *
 * The real implementation -- bridging each of Task 7.1's six tools to
 * its actual Python/HTTP caller (`docs/planner-tool-schemas.md`'s own
 * mapping table: resolve_region/get_data/calculate_statistics/
 * generate_map/get_result_evidence to the real Python functions,
 * run_forecast to the existing POST /forecasts pipeline), and resolving
 * a step's `$step_id.field` references against an already-completed
 * dependency's outputRef -- is deliberately not built by this task; see
 * docs/workflow-execution.md. WorkflowExecutor only depends on this
 * interface, so it is fully testable against a fake today and gets a
 * real dispatcher later with no change to the executor itself -- the
 * same shape ForecastRunner/PythonForecastRunner (Task 6.2) already
 * uses.
 */
public interface WorkflowTaskDispatcher {

    DispatchOutcome dispatch(WorkflowNode node);

    /**
     * Mirrors ForecastOutcome (Task 6.6) exactly: success/output, or a
     * failure marked transient (worth retrying) vs permanent (retrying
     * would only reproduce it).
     */
    record DispatchOutcome(boolean success, String outputRef, String error, boolean transientFailure) {

        public static DispatchOutcome success(String outputRef) {
            return new DispatchOutcome(true, outputRef, null, false);
        }

        public static DispatchOutcome permanentFailure(String error) {
            return new DispatchOutcome(false, null, error, false);
        }

        public static DispatchOutcome transientFailure(String error) {
            return new DispatchOutcome(false, null, error, true);
        }
    }
}
