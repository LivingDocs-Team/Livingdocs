package com.livingdocs.github.repository;

import com.livingdocs.github.entity.ChangeTriggerSource;
import com.livingdocs.github.entity.DocumentationChangeLog;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface DocumentationChangeLogRepository extends JpaRepository<DocumentationChangeLog, String> {

    List<DocumentationChangeLog> findByDocumentIdOrderByCreatedAtDesc(String documentId);

    List<DocumentationChangeLog> findByDocumentIdAndStatusOrderByCreatedAtDesc(
            String documentId,
            String status
    );

    List<DocumentationChangeLog> findByDocumentIdAndTriggerSourceOrderByCreatedAtDesc(
            String documentId,
            ChangeTriggerSource triggerSource
    );

    List<DocumentationChangeLog> findByDocumentIdAndStatusAndTriggerSourceOrderByCreatedAtDesc(
            String documentId,
            String status,
            ChangeTriggerSource triggerSource
    );
}