package com.example.backend.workflow;

public interface WorkflowTaskDispatcher {

    DispatchOutcome dispatch(WorkflowNode node);

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
