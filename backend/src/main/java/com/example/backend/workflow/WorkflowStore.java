package com.example.backend.workflow;

import com.example.backend.workflow.WorkflowNode.Status;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.ObjectMapper;

/**
 * Durable Postgres-backed storage for a Workflow and its nodes, giving
 * `workflows`/`jobs` their first real read/write path. Mirrors
 * ForecastStore's shape: save/find do the domain <-> entity conversion,
 * nothing else in the workflow package needs to know these are Postgres
 * rows under a jsonb dependencies column.
 */
@Repository
public class WorkflowStore {

    private final WorkflowJpaRepository workflows;
    private final JobJpaRepository jobs;
    private final ObjectMapper objectMapper;

    public WorkflowStore(WorkflowJpaRepository workflows, JobJpaRepository jobs, ObjectMapper objectMapper) {
        this.workflows = workflows;
        this.jobs = jobs;
        this.objectMapper = objectMapper;
    }

    /** Upserts the workflow row and every one of its node rows. */
    public void save(Workflow workflow) {
        workflows.save(
                new WorkflowEntity(workflow.id(), workflow.name(), workflow.description(), workflow.createdAt()));

        for (WorkflowNode node : workflow.nodes()) {
            jobs.save(toEntity(workflow.id(), node));
        }
    }

    public Optional<Workflow> find(String workflowId) {
        return workflows.findById(workflowId).map(entity -> {
            List<WorkflowNode> nodes = jobs.findByWorkflowIdOrderByCreatedAtAsc(workflowId).stream()
                    .map(this::toDomain)
                    .toList();

            return new Workflow(
                    entity.getId(), entity.getName(), entity.getDescription(), entity.getCreatedAt(), nodes);
        });
    }

    private JobEntity toEntity(String workflowId, WorkflowNode node) {
        return new JobEntity(
                workflowId + ":" + node.taskId(),
                node.taskId(),
                workflowId,
                node.taskType(),
                node.status().name(),
                objectMapper.writeValueAsString(node.dependencies()),
                node.attempt(),
                node.inputRef(),
                node.outputRef(),
                node.createdAt(),
                node.updatedAt(),
                node.error());
    }

    private WorkflowNode toDomain(JobEntity entity) {
        List<String> dependencies = List.of(objectMapper.readValue(entity.getDependencies(), String[].class));

        return new WorkflowNode(
                entity.getTaskId(),
                entity.getJobType(),
                dependencies,
                Status.valueOf(entity.getStatus()),
                entity.getAttempt(),
                entity.getInputRef(),
                entity.getOutputRef(),
                entity.getCreatedAt(),
                entity.getUpdatedAt(),
                entity.getError());
    }
}
