package com.example.backend.workflow;

import org.springframework.data.jpa.repository.JpaRepository;

public interface WorkflowJpaRepository extends JpaRepository<WorkflowEntity, String> {
}
