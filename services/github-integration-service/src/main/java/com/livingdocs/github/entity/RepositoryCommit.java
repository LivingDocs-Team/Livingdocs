package com.livingdocs.github.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.UUID;

/** LD-72: một commit của repository đã kết nối (mỗi SHA lưu một lần cho mỗi repo). */
@Entity
@Table(name = "github_commits")
public class RepositoryCommit {

    public static final int MAX_MESSAGE_LENGTH = 4000;

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "repository_id", nullable = false)
    private UUID repositoryId;

    @Column(nullable = false, length = 40)
    private String sha;

    @Column(length = 255)
    private String branch;

    @Column(length = MAX_MESSAGE_LENGTH)
    private String message;

    @Column(name = "author_name", length = 255)
    private String authorName;

    @Column(name = "author_login", length = 100)
    private String authorLogin;

    @Column(name = "committed_at")
    private Instant committedAt;

    @Column(name = "html_url", length = 500)
    private String htmlUrl;

    @Enumerated(EnumType.STRING)
    @JdbcTypeCode(SqlTypes.VARCHAR)
    @Column(nullable = false, length = 20)
    private IngestionSource source;

    @Column(name = "received_at", nullable = false, updatable = false)
    private Instant receivedAt;

    @PrePersist
    void onCreate() {
        receivedAt = Instant.now();
    }

    public UUID getId() { return id; }

    public UUID getRepositoryId() { return repositoryId; }
    public void setRepositoryId(UUID repositoryId) { this.repositoryId = repositoryId; }

    public String getSha() { return sha; }
    public void setSha(String sha) { this.sha = sha; }

    public String getBranch() { return branch; }
    public void setBranch(String branch) { this.branch = branch; }

    public String getMessage() { return message; }
    public void setMessage(String message) {
        this.message = message != null && message.length() > MAX_MESSAGE_LENGTH
                ? message.substring(0, MAX_MESSAGE_LENGTH) : message;
    }

    public String getAuthorName() { return authorName; }
    public void setAuthorName(String authorName) { this.authorName = authorName; }

    public String getAuthorLogin() { return authorLogin; }
    public void setAuthorLogin(String authorLogin) { this.authorLogin = authorLogin; }

    public Instant getCommittedAt() { return committedAt; }
    public void setCommittedAt(Instant committedAt) { this.committedAt = committedAt; }

    public String getHtmlUrl() { return htmlUrl; }
    public void setHtmlUrl(String htmlUrl) { this.htmlUrl = htmlUrl; }

    public IngestionSource getSource() { return source; }
    public void setSource(IngestionSource source) { this.source = source; }

    public Instant getReceivedAt() { return receivedAt; }
}
