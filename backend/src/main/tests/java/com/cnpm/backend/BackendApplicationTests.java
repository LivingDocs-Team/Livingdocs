package com.cnpm.backend;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;

import com.cnpm.backend.controller.AdminRoleController;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.cnpm.backend.controller.AdminUserController;
import com.cnpm.backend.entity.AdminUserAudit;
import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.AdminUserAuditRepository;
import com.cnpm.backend.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class BackendApplicationTests {

    @Autowired
    private AdminUserController adminUsers;
    @Autowired
    private AdminRoleController adminRoles;
    @Autowired
    private PlatformTransactionManager transactions;
    @Autowired
    private jakarta.persistence.EntityManager entityManager;
    @Autowired
    private UserRepository users;
    @Autowired
    private AdminUserAuditRepository audit;
    @Autowired
    private JdbcTemplate jdbc;

	@Test
	void contextLoads() {
	}

    @Test
    @Transactional
    void persistsAdministrativeChangesInTheMigratedAuditTable() {
        User actor = saveUser("ADMINISTRATOR");
        User target = saveUser("DEVELOPER");
        var authentication = new TestingAuthenticationToken(actor.getEmail(), null,
                "ROLE_ADMINISTRATOR", "USER_DISABLE", "USER_ASSIGN_ROLE", "USER_AUDIT_VIEW");
        var context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);
        try {
            adminUsers.updateStatus(target.getId(), new AdminUserController.UpdateUserStatusRequest(false),
                    authentication);
            adminUsers.updatePrimaryRole(target.getId(), new AdminUserController.UpdateUserRoleRequest("STAFF"),
                    authentication);
            var actions = jdbc.queryForList("""
                    select action from admin_user_audit
                    where actor_id = ? and target_id = ? order by id
                    """, String.class, actor.getId(), target.getId());
            assertThat(actions).containsExactly("USER_STATUS_CHANGED", "USER_ROLE_CHANGED");
            assertThat(adminUsers.listAudit(0, 1).content()).hasSize(1);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    @Test
    @Transactional
    void retentionDeletesExpiredRowsAndKeepsTheCutoffBoundary() {
        var cutoff = Instant.parse("1900-01-01T00:00:00Z");
        long expired = saveAuditAt(cutoff.minusSeconds(1));
        long boundary = saveAuditAt(cutoff);

        audit.deleteOlderThan(cutoff);

        assertThat(jdbc.queryForList("select id from admin_user_audit where id in (?, ?)",
                Long.class, expired, boundary)).containsExactly(boundary);
    }

    @Test
    @Transactional
    void recordsRoleChangesAndSkipsEquivalentRequests() {
        User actor = saveUser("ADMINISTRATOR");
        var authentication = authenticate(actor, "ROLE_ASSIGN_PERMISSION", "ROLE_VIEW", "USER_AUDIT_VIEW");
        try {
            var before = adminRoles.getRole("STAFF");
            var replacement = before.permissions().contains("ROLE_VIEW")
                    ? List.<String>of() : List.of("ROLE_VIEW");
            var description = new AdminRoleController.UpdateRoleRequest(before.description() + " updated");
            adminRoles.updateRole("staff", description, authentication);
            adminRoles.updateRole("STAFF",
                    new AdminRoleController.UpdateRoleRequest(" " + description.description() + " "), authentication);
            adminRoles.replacePermissions("staff", new AdminRoleController.PermissionAssignment(replacement), authentication);
            var equivalent = replacement.isEmpty() ? replacement : List.of("role_view", "ROLE_VIEW");
            adminRoles.replacePermissions("STAFF", new AdminRoleController.PermissionAssignment(equivalent), authentication);

            var entries = adminUsers.listAudit(0, 100).content().stream()
                    .filter(entry -> actor.getId().equals(entry.actorId())).toList();
            assertThat(entries).hasSize(2);
            var grants = entries.get(0);
            assertThat(grants.action()).isEqualTo("ROLE_PERMISSIONS_CHANGED");
            assertThat(grants.targetRole()).isEqualTo("STAFF");
            assertThat(grants.targetId()).isNull();
            assertThat(grants.occurredAt()).isNotNull();
            assertThat(grants.previousValue()).isEqualTo(String.join(",", before.permissions()));
            assertThat(grants.newValue()).isEqualTo(String.join(",", replacement));
            var metadata = entries.get(1);
            assertThat(metadata.action()).isEqualTo("ROLE_DESCRIPTION_CHANGED");
            assertThat(metadata.previousValue()).isEqualTo(before.description());
            assertThat(metadata.newValue()).isEqualTo(description.description());
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    @Test
    @Transactional
    void roleViewAloneCannotChangeRoleCatalog() {
        User actor = saveUser("STAFF");
        var authentication = authenticate(actor, "ROLE_VIEW");
        try {
            var before = adminRoles.getRole("STAFF");
            assertThatThrownBy(() -> adminRoles.updateRole("STAFF",
                    new AdminRoleController.UpdateRoleRequest("Forbidden edit"), authentication))
                    .isInstanceOf(AccessDeniedException.class);
            assertThatThrownBy(() -> adminRoles.replacePermissions("STAFF",
                    new AdminRoleController.PermissionAssignment(List.of()), authentication))
                    .isInstanceOf(AccessDeniedException.class);
            assertThat(adminRoles.getRole("STAFF")).isEqualTo(before);
            assertThat(jdbc.queryForObject("select count(*) from admin_user_audit where actor_id = ?",
                    Long.class, actor.getId())).isZero();
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    @Test
    void roleAndAuditChangesRollBackTogether() {
        var transaction = new TransactionTemplate(transactions);
        record Before(Long actorId, AdminRoleController.RoleResponse role) { }
        try {
            var before = transaction.execute(status -> {
                User actor = saveUser("ADMINISTRATOR");
                var authentication = authenticate(actor, "ROLE_VIEW", "ROLE_ASSIGN_PERMISSION");
                var role = adminRoles.getRole("STAFF");
                adminRoles.updateRole("STAFF",
                        new AdminRoleController.UpdateRoleRequest("Rolled back"), authentication);
                adminRoles.replacePermissions("STAFF",
                        new AdminRoleController.PermissionAssignment(
                                role.permissions().isEmpty() ? List.of("ROLE_VIEW") : List.of()), authentication);
                entityManager.flush();
                assertThat(adminRoles.getRole("STAFF")).isNotEqualTo(role);
                assertThat(jdbc.queryForObject("select count(*) from admin_user_audit where actor_id = ?",
                        Long.class, actor.getId())).isEqualTo(2L);
                status.setRollbackOnly();
                return new Before(actor.getId(), role);
            });
            assertThat(adminRoles.getRole("STAFF")).isEqualTo(before.role());
            assertThat(jdbc.queryForObject("select count(*) from admin_user_audit where actor_id = ?",
                    Long.class, before.actorId())).isZero();
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private TestingAuthenticationToken authenticate(User actor, String... authorities) {
        var authentication = new TestingAuthenticationToken(actor.getEmail(), null, authorities);
        var context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);
        return authentication;
    }

    private long saveAuditAt(Instant timestamp) {
        long id = audit.save(AdminUserAudit.statusChanged(1L, 2L, true, false)).getId();
        jdbc.update("update admin_user_audit set occurred_at = ? where id = ?",
                OffsetDateTime.ofInstant(timestamp, ZoneOffset.UTC), id);
        return id;
    }

    private User saveUser(String role) {
        String username = UUID.randomUUID().toString();
        User user = new User(username + "@example.test", "test-only", "Test", "User", role, true);
        user.setUsername(username);
        return users.save(user);
    }

}



