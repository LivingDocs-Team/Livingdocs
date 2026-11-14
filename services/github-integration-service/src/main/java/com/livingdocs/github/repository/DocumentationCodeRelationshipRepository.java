package com.livingdocs.github.repository;

import com.livingdocs.github.entity.DocumentationCodeRelationship;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface DocumentationCodeRelationshipRepository extends JpaRepository<DocumentationCodeRelationship, UUID> {
    List<DocumentationCodeRelationship> findByDocumentationId(UUID documentationId);
    List<DocumentationCodeRelationship> findByCodeEntityId(UUID codeEntityId);
    void deleteByDocumentationId(UUID documentationId);
}



