package com.example.backend.workflow;

import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * A named DAG of WorkflowNodes (Task 8.1) -- the shape the `workflows`
 * table (Task 6.3, schema only until now) names but has no real type
 * for yet. Mirrors the Python planner's Plan (question + steps) with a
 * name/description in place of a natural-language question, since a
 * Workflow is not necessarily produced by the planner -- see
 * docs/workflow-dag-schema.md.
 */
public record Workflow(String id, String name, String description, Instant createdAt, List<WorkflowNode> nodes) {

    public Workflow {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(name, "name");
        Objects.requireNonNull(createdAt, "createdAt");
        nodes = List.copyOf(nodes == null ? List.of() : nodes);
    }

    /**
     * The structural half of "this is really a DAG": every dependency
     * must name a real node in this same workflow, no node may depend
     * on itself, task_ids are unique, and the dependency graph has no
     * cycle. This is Task 8.1's own version of the "workflow
     * dependencies" check the handbook's Task 7.2 already does for a
     * Plan's `depends_on` references -- it is deliberately only
     * structural: which task_type a node names, and whether its
     * inputRef is actually resolvable, are Task 8.2 (legal status
     * transitions) and Task 8.3 (real execution)'s concerns, not this
     * one's.
     */
    public List<String> validate() {
        List<String> errors = new ArrayList<>();
        Set<String> taskIds = new HashSet<>();

        for (WorkflowNode node : nodes) {
            if (!taskIds.add(node.taskId())) {
                errors.add("duplicate task_id: '" + node.taskId() + "'");
            }
        }

        for (WorkflowNode node : nodes) {
            for (String dependency : node.dependencies()) {
                if (dependency.equals(node.taskId())) {
                    errors.add("task '" + node.taskId() + "' depends on itself");
                } else if (!taskIds.contains(dependency)) {
                    errors.add(
                            "task '" + node.taskId() + "' depends on unknown task '" + dependency + "'");
                }
            }
        }

        if (errors.isEmpty() && hasCycle()) {
            errors.add("workflow contains a dependency cycle");
        }

        return errors;
    }

    /** Kahn's algorithm: a DAG has a full topological order; a graph with a cycle does not. */
    private boolean hasCycle() {
        Map<String, Integer> remainingDependencies = new HashMap<>();
        Map<String, List<String>> dependents = new HashMap<>();

        for (WorkflowNode node : nodes) {
            remainingDependencies.put(node.taskId(), node.dependencies().size());
        }
        for (WorkflowNode node : nodes) {
            for (String dependency : node.dependencies()) {
                dependents.computeIfAbsent(dependency, key -> new ArrayList<>()).add(node.taskId());
            }
        }

        Deque<String> ready = new ArrayDeque<>();
        remainingDependencies.forEach((taskId, count) -> {
            if (count == 0) {
                ready.add(taskId);
            }
        });

        int visited = 0;
        while (!ready.isEmpty()) {
            String taskId = ready.poll();
            visited++;
            for (String dependent : dependents.getOrDefault(taskId, List.of())) {
                int remaining = remainingDependencies.merge(dependent, -1, Integer::sum);
                if (remaining == 0) {
                    ready.add(dependent);
                }
            }
        }

        return visited != nodes.size();
    }
}
