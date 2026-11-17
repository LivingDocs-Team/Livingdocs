package com.livingdocs.github.dto;

import com.livingdocs.github.entity.ChangeTriggerSource;
import com.livingdocs.github.entity.DocumentationChangeLog;
import java.time.Instant;
import java.util.UUID;

public record DocumentationChangeLogResponse(
        String id,
        String documentId,
        UUID repositoryId,
        Integer versionNumber,
        String action,
        String summary,
        String actorId,
        String actorName,
        String actorRole,
        ChangeTriggerSource triggerSource,
        String status,
        String referenceId,
        Instant createdAt
) {
    public static DocumentationChangeLogResponse from(DocumentationChangeLog entity) {
        return new DocumentationChangeLogResponse(
                entity.getId(),
                entity.getDocumentId(),
                entity.getRepositoryId(),
                entity.getVersionNumber(),
                entity.getAction(),
                entity.getSummary(),
                entity.getActorId(),
                entity.getActorName(),
                entity.getActorRole(),
                entity.getTriggerSource(),
                entity.getStatus(),
                entity.getReferenceId(),
                entity.getCreatedAt()
        );
    }
}