package com.example.backend.workflow;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface JobJpaRepository extends JpaRepository<JobEntity, String> {

    List<JobEntity> findByWorkflowIdOrderByCreatedAtAsc(String workflowId);
}
