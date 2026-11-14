package com.livingdocs.github.repository;

import java.util.List;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import com.livingdocs.github.entity.DocumentWorkflowAudit;

@Repository
public interface DocumentWorkflowAuditRepository extends JpaRepository<DocumentWorkflowAudit, UUID> {
    List<DocumentWorkflowAudit> findByWorkflowIdOrderByCreatedAtAsc(UUID workflowId);
}



