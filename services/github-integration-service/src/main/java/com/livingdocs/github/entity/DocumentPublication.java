package com.livingdocs.github.entity;

import java.time.Instant;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/** GitHub confirmed a commit of an approved document version. Never updated or deleted by the application. */
@Entity
@Table(name = "document_publications")
public class DocumentPublication {
    @Id
    private UUID id;

    @Column(name = "workflow_id", nullable = false, updatable = false)
    private UUID workflowId;

    @Column(name = "document_id", nullable = false, updatable = false, length = 64)
    private String documentId;

    @Column(nullable = false, updatable = false)
    private int version;

    @Column(name = "repository_id", nullable = false, updatable = false)
    private UUID repositoryId;

    @Column(nullable = false, updatable = false, length = 255)
    private String branch;

    @Column(nullable = false, updatable = false, length = 500)
    private String path;

    @Column(name = "commit_sha", nullable = false, updatable = false, length = 64)
    private String commitSha;

    @Column(name = "published_at", nullable = false, updatable = false)
    private Instant publishedAt;

    @Column(name = "published_by", nullable = false, updatable = false, length = 100)
    private String publishedBy;

    protected DocumentPublication() { }

    public DocumentPublication(UUID workflowId, String documentId, int version, UUID repositoryId, String branch,
            String path, String commitSha, String publishedBy) {
        this.id = UUID.randomUUID();
        this.workflowId = workflowId;
        this.documentId = documentId;
        this.version = version;
        this.repositoryId = repositoryId;
        this.branch = branch;
        this.path = path;
        this.commitSha = commitSha;
        this.publishedBy = publishedBy;
        this.publishedAt = Instant.now();
    }

    public UUID getId() { return id; }
    public UUID getWorkflowId() { return workflowId; }
    public String getDocumentId() { return documentId; }
    public int getVersion() { return version; }
    public UUID getRepositoryId() { return repositoryId; }
    public String getBranch() { return branch; }
    public String getPath() { return path; }
    public String getCommitSha() { return commitSha; }
    public Instant getPublishedAt() { return publishedAt; }
    public String getPublishedBy() { return publishedBy; }
}
