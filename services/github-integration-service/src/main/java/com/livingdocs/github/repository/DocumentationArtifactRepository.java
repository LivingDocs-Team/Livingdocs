package com.livingdocs.github.repository;

import com.livingdocs.github.entity.DocumentationArtifact;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface DocumentationArtifactRepository extends JpaRepository<DocumentationArtifact, UUID> {
    Optional<DocumentationArtifact> findByGenerationJobId(String generationJobId);
    Optional<DocumentationArtifact> findByIdAndOwnerUserId(UUID id, String ownerUserId);
    List<DocumentationArtifact> findByRepositoryIdAndOwnerUserIdOrderByCreatedAtDesc(UUID repositoryId, String ownerUserId);
}
