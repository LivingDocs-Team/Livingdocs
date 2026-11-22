package com.livingdocs.github.entity;

import java.time.Instant;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "document_workflow_audit")
public class DocumentWorkflowAudit {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "workflow_id", nullable = false)
    private UUID workflowId;

    @Column(name = "actor_user_id", nullable = false, length = 100)
    private String actorUserId;

    @Column(name = "actor_role", length = 40)
    private String actorRole;

    @Column(name = "previous_reviewer_user_id", length = 100)
    private String previousReviewerUserId;

    @Column(name = "new_reviewer_user_id", length = 100)
    private String newReviewerUserId;

    @Column(nullable = false, length = 40)
    private String action;

    @Column(name = "previous_status", length = 40)
    private String previousStatus;

    @Column(name = "new_status", nullable = false, length = 40)
    private String newStatus;

    @Column(length = 2000)
    private String comment;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "trigger_source", length = 40, updatable = false)
    private String triggerSource;

    @Column(name = "document_version")
    private Integer documentVersion;

    @Column(name = "section_start_offset")
    private Integer sectionStartOffset;

    @Column(name = "section_end_offset")
    private Integer sectionEndOffset;

    @Column(name = "section_quote", length = 4000)
    private String sectionQuote;

    public Integer getSectionStartOffset() { return sectionStartOffset; }
    public Integer getSectionEndOffset() { return sectionEndOffset; }
    public String getSectionQuote() { return sectionQuote; }

    public void setSectionFeedback(int startOffset, int endOffset, String quote) {
        this.sectionStartOffset = startOffset;
        this.sectionEndOffset = endOffset;
        this.sectionQuote = quote;
    }

    public Integer getDocumentVersion() { return documentVersion; }

    public void setDocumentVersion(Integer documentVersion) {
        this.documentVersion = documentVersion;
    }

    protected DocumentWorkflowAudit() { }

    public DocumentWorkflowAudit(UUID workflowId, String actorUserId, String action,
            String previousStatus, String newStatus, String comment) {
        this(workflowId, actorUserId, action, previousStatus, newStatus, comment, null, null, null);
    }

    public DocumentWorkflowAudit(UUID workflowId, String actorUserId, String action,
            String previousStatus, String newStatus, String comment,
            String previousReviewerUserId, String newReviewerUserId) {
        this(workflowId, actorUserId, action, previousStatus, newStatus, comment,
                previousReviewerUserId, newReviewerUserId, null);
    }

    public DocumentWorkflowAudit(UUID workflowId, String actorUserId, String action,
            String previousStatus, String newStatus, String comment,
            String previousReviewerUserId, String newReviewerUserId, String actorRole) {
        this(workflowId, actorUserId, action, previousStatus, newStatus, comment,
                previousReviewerUserId, newReviewerUserId, actorRole, Instant.now());
    }

    public DocumentWorkflowAudit(UUID workflowId, String actorUserId, String action,
            String previousStatus, String newStatus, String comment,
            String previousReviewerUserId, String newReviewerUserId, String actorRole, Instant createdAt) {
        this.workflowId = workflowId;
        this.actorUserId = actorUserId;
        this.actorRole = actorRole;
        this.action = action;
        this.previousStatus = previousStatus;
        this.newStatus = newStatus;
        this.comment = comment;
        this.previousReviewerUserId = previousReviewerUserId;
        this.newReviewerUserId = newReviewerUserId;
        this.createdAt = createdAt;
    }

    public UUID getId() { return id; }
    public UUID getWorkflowId() { return workflowId; }
    public String getActorUserId() { return actorUserId; }
    public String getActorRole() { return actorRole; }
    public String getTriggerSource() { return triggerSource; }
    public void setTriggerSource(String triggerSource) { this.triggerSource = triggerSource; }
    public String getPreviousReviewerUserId() { return previousReviewerUserId; }
    public String getNewReviewerUserId() { return newReviewerUserId; }
    public String getAction() { return action; }
    public String getPreviousStatus() { return previousStatus; }
    public String getNewStatus() { return newStatus; }
    public String getComment() { return comment; }
    public Instant getCreatedAt() { return createdAt; }
}
