package com.cnpm.backend.entity;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "admin_user_audit")
public class AdminUserAudit {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, updatable = false)
    private Long actorId;

    @Column(updatable = false)
    private Long targetId;

    @Column(updatable = false, length = 30)
    private String targetRole;

    @Column(updatable = false, length = 40)
    private String targetEvent;

    @Column(nullable = false, updatable = false, length = 30)
    private String action;

    @Column(nullable = false, updatable = false, columnDefinition = "text")
    private String previousValue;

    @Column(nullable = false, updatable = false, columnDefinition = "text")
    private String newValue;

    @Column(nullable = false, updatable = false)
    private Instant occurredAt;

    protected AdminUserAudit() {
    }

    private AdminUserAudit(Long actorId, Long targetId, String targetRole, String action, String previousValue, String newValue) {
        this.actorId = actorId;
        this.targetId = targetId;
        this.targetRole = targetRole;
        this.action = action;
        this.previousValue = previousValue;
        this.newValue = newValue;
        this.occurredAt = Instant.now();
    }

    public static AdminUserAudit statusChanged(Long actorId, Long targetId, boolean before, boolean after) {
        return new AdminUserAudit(actorId, targetId, null, "USER_STATUS_CHANGED", String.valueOf(before), String.valueOf(after));
    }

    public static AdminUserAudit roleChanged(Long actorId, Long targetId, String before, String after) {
        return new AdminUserAudit(actorId, targetId, null, "USER_ROLE_CHANGED", before, after);
    }

    public static AdminUserAudit roleCatalogChanged(Long actorId, String role, String action,
            String before, String after) {
        return new AdminUserAudit(actorId, null, role, action, before, after);
    }

    public static AdminUserAudit profileChanged(Long actorId, Long targetId, String changedFields) {
        return new AdminUserAudit(actorId, targetId, null, "USER_PROFILE_CHANGED", "", changedFields);
    }

    public static AdminUserAudit notificationPolicyChanged(Long actorId, String event, String action, String newValue) {
        var entry = new AdminUserAudit(actorId, null, null, action, "", newValue);
        entry.targetEvent = event;
        return entry;
    }

    public String getTargetEvent() { return targetEvent; }
    public String getTargetRole() { return targetRole; }
    public Long getId() { return id; }
    public Long getActorId() { return actorId; }
    public Long getTargetId() { return targetId; }
    public String getAction() { return action; }
    public String getPreviousValue() { return previousValue; }
    public String getNewValue() { return newValue; }
    public Instant getOccurredAt() { return occurredAt; }
}
