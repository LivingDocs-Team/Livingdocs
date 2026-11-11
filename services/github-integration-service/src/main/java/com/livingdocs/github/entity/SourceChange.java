package com.livingdocs.github.entity;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.OrderBy;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * LD-116: thay đổi mã nguồn của một commit (trên nhánh mặc định) hoặc của một Pull Request.
 * PENDING nghĩa là đã phát hiện xong và đang chờ bước cập nhật tài liệu (LD-128) đọc.
 * documentsStatus (LD-122): PENDING đang tìm tài liệu bị ảnh hưởng, FOUND đã tìm xong
 * (xem affectedDocuments, có thể rỗng), FAILED ai-service lỗi (gọi retry); null khi status là FAILED.
 */
@Entity
@Table(name = "source_changes")
public class SourceChange {

    public enum Trigger { COMMIT, PULL_REQUEST }

    public enum Status { PENDING, FAILED }

    public enum DocumentsStatus { PENDING, FOUND, FAILED }

    private static final int MAX_ERROR_LENGTH = 500;

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "repository_id", nullable = false)
    private UUID repositoryId;

    @Enumerated(EnumType.STRING)
    @JdbcTypeCode(SqlTypes.VARCHAR)
    @Column(name = "trigger_type", nullable = false, length = 20)
    private Trigger triggerType;

    @Column(name = "commit_sha", nullable = false, length = 40)
    private String commitSha;

    @Column(name = "pr_number")
    private Integer pullRequestNumber;

    @Enumerated(EnumType.STRING)
    @JdbcTypeCode(SqlTypes.VARCHAR)
    @Column(nullable = false, length = 20)
    private Status status;

    @Column(name = "error_code", length = 50)
    private String errorCode;

    @Column(name = "error_message", length = MAX_ERROR_LENGTH)
    private String errorMessage;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @OneToMany(mappedBy = "sourceChange", cascade = CascadeType.ALL, orphanRemoval = true)
    @OrderBy("path")
    private List<SourceChangeFile> files = new ArrayList<>();

    @Enumerated(EnumType.STRING)
    @JdbcTypeCode(SqlTypes.VARCHAR)
    @Column(name = "documents_status", length = 20)
    private DocumentsStatus documentsStatus;

    @Column(name = "documents_error_code", length = 50)
    private String documentsErrorCode;

    @Column(name = "documents_error_message", length = MAX_ERROR_LENGTH)
    private String documentsErrorMessage;

    // DESC: DIRECT trước DEPENDENT
    @OneToMany(mappedBy = "sourceChange", cascade = CascadeType.ALL, orphanRemoval = true)
    @OrderBy("dependency DESC, title, sectionPath")
    private List<AffectedDocument> affectedDocuments = new ArrayList<>();

    @PrePersist
    void onCreate() {
        createdAt = Instant.now();
        updatedAt = createdAt;
    }

    @PreUpdate
    void onUpdate() {
        updatedAt = Instant.now();
    }

    /** Kết quả phát hiện thành công: thay toàn bộ danh sách file và xoá lỗi cũ (nếu có). */
    public void markPending(List<SourceChangeFile> detectedFiles) {
        status = Status.PENDING;
        errorCode = null;
        errorMessage = null;
        files.clear();
        for (SourceChangeFile file : detectedFiles) {
            file.setSourceChange(this);
            files.add(file);
        }
        setDocuments(DocumentsStatus.PENDING, null, null, List.of()); // file đổi thì tìm lại tài liệu
    }

    public void markFailed(String code, String message) {
        status = Status.FAILED;
        errorCode = code;
        errorMessage = cut(message);
        files.clear();
        setDocuments(null, null, null, List.of());
    }

    /** LD-122: kết quả tìm tài liệu bị ảnh hưởng, thay toàn bộ danh sách cũ. */
    public void markDocumentsFound(List<AffectedDocument> documents) {
        setDocuments(DocumentsStatus.FOUND, null, null, documents);
    }

    public void markDocumentsFailed(String code, String message) {
        setDocuments(DocumentsStatus.FAILED, code, cut(message), List.of());
    }

    private void setDocuments(DocumentsStatus newStatus, String code, String message, List<AffectedDocument> documents) {
        documentsStatus = newStatus;
        documentsErrorCode = code;
        documentsErrorMessage = message;
        affectedDocuments.clear();
        for (AffectedDocument document : documents) {
            document.setSourceChange(this);
            affectedDocuments.add(document);
        }
    }

    private static String cut(String message) {
        return message != null && message.length() > MAX_ERROR_LENGTH ? message.substring(0, MAX_ERROR_LENGTH) : message;
    }

    public UUID getId() { return id; }

    public UUID getRepositoryId() { return repositoryId; }
    public void setRepositoryId(UUID repositoryId) { this.repositoryId = repositoryId; }

    public Trigger getTriggerType() { return triggerType; }
    public void setTriggerType(Trigger triggerType) { this.triggerType = triggerType; }

    public String getCommitSha() { return commitSha; }
    public void setCommitSha(String commitSha) { this.commitSha = commitSha; }

    public Integer getPullRequestNumber() { return pullRequestNumber; }
    public void setPullRequestNumber(Integer pullRequestNumber) { this.pullRequestNumber = pullRequestNumber; }

    public Status getStatus() { return status; }

    public String getErrorCode() { return errorCode; }

    public String getErrorMessage() { return errorMessage; }

    public Instant getCreatedAt() { return createdAt; }

    public Instant getUpdatedAt() { return updatedAt; }

    public List<SourceChangeFile> getFiles() { return files; }

    public DocumentsStatus getDocumentsStatus() { return documentsStatus; }

    public String getDocumentsErrorCode() { return documentsErrorCode; }

    public String getDocumentsErrorMessage() { return documentsErrorMessage; }

    public List<AffectedDocument> getAffectedDocuments() { return affectedDocuments; }
}
