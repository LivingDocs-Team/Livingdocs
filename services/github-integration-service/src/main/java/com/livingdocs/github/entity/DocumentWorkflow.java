package com.livingdocs.github.entity;

import java.time.Instant;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "document_workflows")
public class DocumentWorkflow {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "document_id", nullable = false, unique = true, length = 64)
    private String documentId;

    @Column(name = "document_title", nullable = false, length = 200)
    private String documentTitle;

    @Column(name = "owner_user_id", nullable = false, length = 100, updatable = false)
    private String ownerUserId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 40)
    private DocumentWorkflowStatus status;

    @Column(name = "submitted_document_version")
    private Integer submittedDocumentVersion;

    @Column(name = "reviewer_user_id", length = 100)
    private String reviewerUserId;

    @Enumerated(EnumType.STRING)
    @Column(name = "staff_review_result", length = 30)
    private StaffReviewResult staffReviewResult;

    @Column(name = "staff_comment", length = 2000)
    private String staffComment;

    @Column(name = "manager_user_id", length = 100)
    private String managerUserId;

    @Enumerated(EnumType.STRING)
    @Column(name = "manager_decision", length = 20)
    private ManagerDecision managerDecision;

    @Column(name = "manager_comment", length = 2000)
    private String managerComment;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Column(name = "submitted_at")
    private Instant submittedAt;

    @Column(name = "reviewed_at")
    private Instant reviewedAt;

    @Column(name = "decided_at")
    private Instant decidedAt;

    @Version
    @Column(name = "optimistic_version", nullable = false)
    private long optimisticVersion;

    protected DocumentWorkflow() { }

    public DocumentWorkflow(String documentId, String documentTitle, String ownerUserId) {
        this.documentId = documentId;
        this.documentTitle = documentTitle;
        this.ownerUserId = ownerUserId;
        this.status = DocumentWorkflowStatus.DRAFT;
    }

    @PrePersist
    void onCreate() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    void onUpdate() { updatedAt = Instant.now(); }

    public UUID getId() { return id; }
    public String getDocumentId() { return documentId; }
    public String getDocumentTitle() { return documentTitle; }
    public String getOwnerUserId() { return ownerUserId; }
    public DocumentWorkflowStatus getStatus() { return status; }
    public Integer getSubmittedDocumentVersion() { return submittedDocumentVersion; }
    public String getReviewerUserId() { return reviewerUserId; }
    public StaffReviewResult getStaffReviewResult() { return staffReviewResult; }
    public String getStaffComment() { return staffComment; }
    public String getManagerUserId() { return managerUserId; }
    public ManagerDecision getManagerDecision() { return managerDecision; }
    public String getManagerComment() { return managerComment; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public Instant getSubmittedAt() { return submittedAt; }
    public Instant getReviewedAt() { return reviewedAt; }
    public Instant getDecidedAt() { return decidedAt; }
    public long getOptimisticVersion() { return optimisticVersion; }

    public void submit(int documentVersion) {
        status = DocumentWorkflowStatus.PENDING_STAFF_REVIEW;
        submittedDocumentVersion = documentVersion;
        reviewerUserId = null;
        staffReviewResult = null;
        staffComment = null;
        managerUserId = null;
        managerDecision = null;
        managerComment = null;
        submittedAt = Instant.now();
        reviewedAt = null;
        decidedAt = null;
    }
    public void startRollbackReview(int documentVersion) {
    status = DocumentWorkflowStatus.PENDING_STAFF_REVIEW;
    submittedDocumentVersion = documentVersion;

    reviewerUserId = null;
    staffReviewResult = null;
    staffComment = null;

    managerUserId = null;
    managerDecision = null;
    managerComment = null;

    submittedAt = Instant.now();
    reviewedAt = null;
    decidedAt = null;
 }
    public void claim(String reviewerUserId) {
        status = DocumentWorkflowStatus.STAFF_REVIEWING;
        this.reviewerUserId = reviewerUserId;
    }

    public void releaseClaim() {
        status = DocumentWorkflowStatus.PENDING_STAFF_REVIEW;
        reviewerUserId = null;
    }

    public void reassignClaim(String reviewerUserId) {
        status = DocumentWorkflowStatus.STAFF_REVIEWING;
        this.reviewerUserId = reviewerUserId;
    }

    public void review(StaffReviewResult result, String comment) {
        staffReviewResult = result;
        staffComment = comment;
        reviewedAt = Instant.now();
        status = result == StaffReviewResult.PASSED
                ? DocumentWorkflowStatus.PENDING_MANAGER_APPROVAL
                : DocumentWorkflowStatus.CHANGES_REQUESTED;
    }

    public void decide(String managerUserId, ManagerDecision decision, String comment) {
        this.managerUserId = managerUserId;
        managerDecision = decision;
        managerComment = comment;
        decidedAt = Instant.now();
        status = decision == ManagerDecision.APPROVED
                ? DocumentWorkflowStatus.APPROVED : DocumentWorkflowStatus.REJECTED;
    }
}
