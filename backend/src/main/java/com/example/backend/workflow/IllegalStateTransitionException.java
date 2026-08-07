package com.example.backend.workflow;

import com.example.backend.workflow.WorkflowNode.Status;

/**
 * Raised by WorkflowStateMachine.transition when the requested status
 * change is not one of the legal edges Task 8.2 defines -- the same
 * "reject, don't silently allow" treatment Task 7.2's plan validator
 * gives an invalid Plan.
 */
public class IllegalStateTransitionException extends IllegalStateException {

    public IllegalStateTransitionException(String taskId, Status from, Status to) {
        super("task '" + taskId + "': illegal transition " + from + " -> " + to);
    }
}
