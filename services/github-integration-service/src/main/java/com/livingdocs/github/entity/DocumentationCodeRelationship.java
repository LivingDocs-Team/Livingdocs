package com.livingdocs.github.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "documentation_code_relationships")
public class DocumentationCodeRelationship {
    @Id
    private UUID id;

    @Column(name = "documentation_id", nullable = false)
    private UUID documentationId;

    @Column(name = "code_entity_id", nullable = false)
    private UUID codeEntityId;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @PrePersist
    void onCreate() { if (id == null) id = UUID.randomUUID(); if (createdAt == null) createdAt = Instant.now(); }

    public UUID getId() { return id; }
    public UUID getDocumentationId() { return documentationId; }
    public void setDocumentationId(UUID documentationId) { this.documentationId = documentationId; }
    public UUID getCodeEntityId() { return codeEntityId; }
    public void setCodeEntityId(UUID codeEntityId) { this.codeEntityId = codeEntityId; }
    public Instant getCreatedAt() { return createdAt; }
}



