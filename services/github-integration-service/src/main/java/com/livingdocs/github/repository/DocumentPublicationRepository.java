package com.livingdocs.github.repository;

import java.util.List;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

import com.livingdocs.github.entity.DocumentPublication;

public interface DocumentPublicationRepository extends JpaRepository<DocumentPublication, UUID> {
    boolean existsByWorkflowIdAndVersion(UUID workflowId, int version);

    List<DocumentPublication> findByWorkflowIdOrderByVersionDesc(UUID workflowId);
}
