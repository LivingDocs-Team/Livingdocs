package com.cnpm.backend.controller;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.time.OffsetDateTime;
import java.util.List;

import com.cnpm.backend.entity.AdminUserAudit;
import com.cnpm.backend.repository.AdminUserAuditRepository;
import com.cnpm.backend.repository.UserRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/admin/notification-policies")
@PreAuthorize("hasAnyRole('ADMIN', 'ADMINISTRATOR') and @systemAdminAccess.allows(authentication)")
public class AdminNotificationPolicyController {
    private final JdbcTemplate jdbc;
    private final UserRepository users;
    private final AdminUserAuditRepository audit;

    public AdminNotificationPolicyController(JdbcTemplate jdbc, UserRepository users, AdminUserAuditRepository audit) {
        this.jdbc = jdbc;
        this.users = users;
        this.audit = audit;
    }

    @GetMapping
    public PolicyList list() {
        var policies = jdbc.query("""
                SELECT event, recipients, enabled, updated_at FROM notification_policies ORDER BY event
                """, this::readPolicy);
        return new PolicyList(List.of(Event.values()), policies);
    }

    @PutMapping("/{event}")
    @Transactional
    public Policy put(@PathVariable Event event, @Valid @RequestBody PolicyRequest policy,
            Authentication authentication) {
        Long actorId = AdminUserController.findAuthenticatedUser(authentication, users).getId();
        String[] recipients = policy.recipients().stream().distinct().toArray(String[]::new);
        var saved = jdbc.query("""
                INSERT INTO notification_policies (event, recipients, enabled)
                VALUES (?, ?, ?)
                ON CONFLICT (event) DO UPDATE
                    SET recipients = excluded.recipients, enabled = excluded.enabled, updated_at = now()
                RETURNING event, recipients, enabled, updated_at
                """, statement -> {
            statement.setString(1, event.name());
            statement.setObject(2, recipients, Types.ARRAY);
            statement.setBoolean(3, policy.enabled());
        }, this::readPolicy).getFirst();
        audit.save(AdminUserAudit.notificationPolicyChanged(actorId, event.name(), "NOTIFICATION_POLICY_SAVED",
                saved.enabled() ? "ENABLED" : "DISABLED"));
        return saved;
    }

    @DeleteMapping("/{event}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @Transactional
    public void delete(@PathVariable Event event, Authentication authentication) {
        Long actorId = AdminUserController.findAuthenticatedUser(authentication, users).getId();
        if (jdbc.update("DELETE FROM notification_policies WHERE event = ?", event.name()) > 0) {
            audit.save(AdminUserAudit.notificationPolicyChanged(actorId, event.name(), "NOTIFICATION_POLICY_DELETED", ""));
        }
    }

    private Policy readPolicy(ResultSet row, int rowNumber) throws SQLException {
        var array = row.getArray("recipients");
        try {
            return new Policy(Event.valueOf(row.getString("event")), List.of((String[]) array.getArray()),
                    row.getBoolean("enabled"), row.getObject("updated_at", OffsetDateTime.class));
        } finally {
            array.free();
        }
    }

    public enum Event {
        REPOSITORY_CONNECTED, DOCUMENT_SUBMITTED, DOCUMENT_APPROVED, DOCUMENT_REJECTED,
        AI_JOB_COMPLETED, AI_JOB_FAILED
    }

    public record PolicyRequest(@NotNull @Size(min = 1, max = 50)
                                List<@NotBlank @Email @Size(max = 254) String> recipients,
                                @NotNull Boolean enabled) {}
    public record Policy(Event event, List<String> recipients, boolean enabled, OffsetDateTime updatedAt) {}
    public record PolicyList(List<Event> supportedEvents, List<Policy> policies) {}
}
