package com.example.backend.workflow;

import com.example.backend.workflow.WorkflowNode.Status;

public class IllegalStateTransitionException extends IllegalStateException {

    public IllegalStateTransitionException(String taskId, Status from, Status to) {
        super("task '" + taskId + "': illegal transition " + from + " -> " + to);
    }
}
