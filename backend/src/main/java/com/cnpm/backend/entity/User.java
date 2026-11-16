
package com.cnpm.backend.entity;

import java.time.LocalDateTime;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

@Entity
@Table(name = "users")
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 50)
    private String username;

    @Column(nullable = false, unique = true, length = 255)
    private String email;

    @Column(name = "github_id", unique = true, length = 50)
    private String githubId;

    @Column(nullable = false, length = 255)
    private String password;

    @Column(name = "first_name", nullable = false)
    private String firstName;

    @Column(name = "last_name", nullable = false)
    private String lastName;

    @Column(nullable = false, length = 30)
    private String role = "DEVELOPER";

    // LD-51: also the "Email updates" notification preference.
    @Column(name = "notification_enabled", nullable = false)
    private boolean notificationEnabled = true;

    // LD-51: other notification preferences; existing accounts keep them on when Hibernate adds the columns.
    @Column(name = "notify_document_changes", nullable = false, columnDefinition = "boolean default true")
    private boolean notifyDocumentChanges = true;

    @Column(name = "notify_review_requests", nullable = false, columnDefinition = "boolean default true")
    private boolean notifyReviewRequests = true;

    @Column(name = "notify_system", nullable = false, columnDefinition = "boolean default true")
    private boolean notifySystem = true;

    // Existing accounts remain enabled when Hibernate adds this column.
    @Column(nullable = false, columnDefinition = "boolean default true")
    private boolean active = true;

    @Column(name = "created_at", nullable = false,
            updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    public User() {
    }

    public User(String email, String password, String firstName,
                String lastName, String role,
                boolean notificationEnabled) {
        this.email = email;
        this.password = password;
        this.firstName = firstName;
        this.lastName = lastName;
        this.role = role;
        this.notificationEnabled = notificationEnabled;
    }

    @PrePersist
    protected void onCreate() {
        LocalDateTime now = LocalDateTime.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }

    public String getFirstName() {
        return firstName;
    }

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public void setLastName(String lastName) {
        this.lastName = lastName;
    }

    public String getRole() {
        return role;
    }

    public void setRole(String role) {
        this.role = role;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }

    public boolean isNotificationEnabled() {
        return notificationEnabled;
    }

    public void setNotificationEnabled(boolean notificationEnabled) {
        this.notificationEnabled = notificationEnabled;
    }

    public boolean isNotifyDocumentChanges() {
        return notifyDocumentChanges;
    }

    public void setNotifyDocumentChanges(boolean notifyDocumentChanges) {
        this.notifyDocumentChanges = notifyDocumentChanges;
    }

    public boolean isNotifyReviewRequests() {
        return notifyReviewRequests;
    }

    public void setNotifyReviewRequests(boolean notifyReviewRequests) {
        this.notifyReviewRequests = notifyReviewRequests;
    }

    public boolean isNotifySystem() {
        return notifySystem;
    }

    public void setNotifySystem(boolean notifySystem) {
        this.notifySystem = notifySystem;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }

    public String getGithubId() {
        return githubId;
    }

    public void setGithubId(String githubId) {
        this.githubId = githubId;
    }
}
