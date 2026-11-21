package com.livingdocs.github.entity;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "documentation_change_logs")
public class DocumentationChangeLog {

    @Id
    @Column(length = 64, nullable = false)
    private String id;

    @Column(name = "document_id", length = 64, nullable = false)
    private String documentId;

    @Column(name = "repository_id")
    private UUID repositoryId;

    @Column(name = "version_number")
    private Integer versionNumber;

    @Column(length = 64, nullable = false)
    private String action;

    @Column(length = 500, nullable = false)
    private String summary;

    @Column(name = "actor_id", length = 128)
    private String actorId;

    @Column(name = "actor_name", length = 255)
    private String actorName;

    @Column(name = "actor_role", length = 64, nullable = false)
    private String actorRole;

    @Enumerated(EnumType.STRING)
    @Column(name = "trigger_source", length = 64, nullable = false)
    private ChangeTriggerSource triggerSource;

    @Column(length = 64, nullable = false)
    private String status;

    @Column(name = "reference_id", length = 128)
    private String referenceId;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @PrePersist
    public void prePersist() {
        if (this.id == null) {
            this.id = UUID.randomUUID().toString();
        }
        if (this.createdAt == null) {
            this.createdAt = Instant.now();
        }
        if (this.actorRole == null || this.actorRole.isBlank()) {
            this.actorRole = "SYSTEM";
        }
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getDocumentId() {
        return documentId;
    }

    public void setDocumentId(String documentId) {
        this.documentId = documentId;
    }

    public UUID getRepositoryId() {
        return repositoryId;
    }

    public void setRepositoryId(UUID repositoryId) {
        this.repositoryId = repositoryId;
    }

    public Integer getVersionNumber() {
        return versionNumber;
    }

    public void setVersionNumber(Integer versionNumber) {
        this.versionNumber = versionNumber;
    }

    public String getAction() {
        return action;
    }

    public void setAction(String action) {
        this.action = action;
    }

    public String getSummary() {
        return summary;
    }

    public void setSummary(String summary) {
        this.summary = summary;
    }

    public String getActorId() {
        return actorId;
    }

    public void setActorId(String actorId) {
        this.actorId = actorId;
    }

    public String getActorName() {
        return actorName;
    }

    public void setActorName(String actorName) {
        this.actorName = actorName;
    }

    public String getActorRole() {
        return actorRole;
    }

    public void setActorRole(String actorRole) {
        this.actorRole = actorRole;
    }

    public ChangeTriggerSource getTriggerSource() {
        return triggerSource;
    }

    public void setTriggerSource(ChangeTriggerSource triggerSource) {
        this.triggerSource = triggerSource;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getReferenceId() {
        return referenceId;
    }

    public void setReferenceId(String referenceId) {
        this.referenceId = referenceId;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }
}