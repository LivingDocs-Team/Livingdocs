package com.livingdocs.github.dto;

import com.livingdocs.github.entity.DocumentationArtifact;

import java.time.Instant;
import java.util.UUID;

public record DocumentationArtifactResponse(UUID id, UUID repositoryId, String generationJobId,
                                            String markdown, String sourceCommit, Instant createdAt) {
    public static DocumentationArtifactResponse from(DocumentationArtifact artifact) {
        return new DocumentationArtifactResponse(artifact.getId(), artifact.getRepositoryId(),
                artifact.getGenerationJobId(), artifact.getMarkdown(), artifact.getSourceCommit(), artifact.getCreatedAt());
    }
}



