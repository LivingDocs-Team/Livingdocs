package com.livingdocs.github.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "code_entities")
public class CodeEntity {
    @Id
    private UUID id;

    @Column(name = "repository_id", nullable = false)
    private UUID repositoryId;

    @Column(name = "stable_key", nullable = false, length = 64)
    private String stableKey;

    @Column(name = "entity_type", nullable = false, length = 30)
    private String entityType;

    @Column(nullable = false, length = 500)
    private String name;

    @Column(nullable = false, length = 1000)
    private String path;

    @Column(name = "line_start")
    private Integer lineStart;

    @Column(name = "line_end")
    private Integer lineEnd;

    @Column(name = "source_url", nullable = false, length = 2000)
    private String sourceUrl;

    @Column(name = "source_commit", length = 64)
    private String sourceCommit;

    @Column(nullable = false)
    private boolean active = true;

    @Column(name = "last_seen_at", nullable = false)
    private Instant lastSeenAt;

    @PrePersist
    void onCreate() { if (id == null) id = UUID.randomUUID(); if (lastSeenAt == null) lastSeenAt = Instant.now(); }

    @PreUpdate
    void onUpdate() { lastSeenAt = Instant.now(); }

    public UUID getId() { return id; }
    public UUID getRepositoryId() { return repositoryId; }
    public void setRepositoryId(UUID repositoryId) { this.repositoryId = repositoryId; }
    public String getStableKey() { return stableKey; }
    public void setStableKey(String stableKey) { this.stableKey = stableKey; }
    public String getEntityType() { return entityType; }
    public void setEntityType(String entityType) { this.entityType = entityType; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getPath() { return path; }
    public void setPath(String path) { this.path = path; }
    public Integer getLineStart() { return lineStart; }
    public void setLineStart(Integer lineStart) { this.lineStart = lineStart; }
    public Integer getLineEnd() { return lineEnd; }
    public void setLineEnd(Integer lineEnd) { this.lineEnd = lineEnd; }
    public String getSourceUrl() { return sourceUrl; }
    public void setSourceUrl(String sourceUrl) { this.sourceUrl = sourceUrl; }
    public String getSourceCommit() { return sourceCommit; }
    public void setSourceCommit(String sourceCommit) { this.sourceCommit = sourceCommit; }
    public boolean isActive() { return active; }
    public void setActive(boolean active) { this.active = active; }
    public Instant getLastSeenAt() { return lastSeenAt; }
}



