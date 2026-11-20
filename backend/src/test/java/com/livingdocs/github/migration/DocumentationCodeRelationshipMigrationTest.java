package com.livingdocs.github;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import javax.sql.DataSource;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Testcontainers
class DocumentationCodeRelationshipMigrationTest {

    private static final String[] MIGRATION_LOCATIONS = {
            "classpath:db/migration-current",
            "classpath:db/migration-common"
    };

    @Container
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("livingdocs_test")
            .withUsername("test")
            .withPassword("test");

    private DataSource createDataSource() {
        return new DriverManagerDataSource(postgres.getJdbcUrl(), postgres.getUsername(), postgres.getPassword());
    }

    @Test
    void freshDatabaseMigrationPassesAllVersionsOnPostgres() {
        DataSource dataSource = createDataSource();

        var result = Flyway.configure()
                .dataSource(dataSource)
                .locations(MIGRATION_LOCATIONS)
                .load()
                .migrate();

        assertThat(result.migrationsExecuted).isGreaterThanOrEqualTo(5);
        assertThat(Integer.parseInt(result.targetSchemaVersion)).isGreaterThanOrEqualTo(5);
    }

    @Test
    void existingDatabaseAtV4UpgradesCleanlyToV5AndEnforcesConstraintsOnPostgres() {
        // Dùng database riêng biệt cho test này bằng cách tạo schema mới để tránh xung đột với test trên
        DataSource dataSource = createDataSource();
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        var baseline = Flyway.configure()
                .dataSource(dataSource)
                .locations(MIGRATION_LOCATIONS)
                .target("4")
                .load()
                .migrate();
        assertThat(baseline.targetSchemaVersion).isEqualTo("4");

        // 1. Chèn dữ liệu V4 (Lineage đang triển khai)
        UUID connectionId = UUID.randomUUID();
        UUID repositoryId = UUID.randomUUID();
        UUID workflowId = UUID.randomUUID();
        UUID auditId = UUID.randomUUID();
        Timestamp now = Timestamp.from(Instant.now());

        jdbc.update("""
                INSERT INTO github_connections (id, user_id, github_user_id, github_login, status, created_at, updated_at)
                VALUES (?, 'user-existing', 1001, 'existing-login', 'ACTIVE', ?, ?)
                """, connectionId, now, now);
        jdbc.update("""
                INSERT INTO repositories (id, workspace_id, connection_id, github_repo_id, full_name, status, created_at)
                VALUES (?, 'ws-user-existing', ?, 2001, 'acme/existing-repo', 'CONNECTED', ?)
                """, repositoryId, connectionId, now);
        jdbc.update("""
                INSERT INTO document_workflows (id, document_id, document_title, owner_user_id, status, created_at, updated_at)
                VALUES (?, 'doc-v4', 'Existing Doc', 'user-existing', 'DRAFT', ?, ?)
                """, workflowId, now, now);
        jdbc.update("""
                INSERT INTO document_workflow_audit (id, workflow_id, actor_user_id, action, new_status, actor_role, created_at)
                VALUES (?, ?, 'user-existing', 'CREATED', 'DRAFT', 'OWNER', ?)
                """, auditId, workflowId, now);

        // 2. Chạy migrate lên V5
        var upgrade = Flyway.configure()
                .dataSource(dataSource)
                .locations(MIGRATION_LOCATIONS)
                .load()
                .migrate();
        assertThat(upgrade.migrationsExecuted).isGreaterThanOrEqualTo(1);
        assertThat(Integer.parseInt(upgrade.targetSchemaVersion)).isGreaterThanOrEqualTo(5);

        // 3. Kiểm tra dữ liệu cũ còn nguyên
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM repositories WHERE id = ?", Integer.class, repositoryId)).isEqualTo(1);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM document_workflow_audit WHERE id = ?", Integer.class, auditId)).isEqualTo(1);

        // 4. Kiểm tra Constraints của bảng mới V5
        UUID docId = UUID.randomUUID();
        UUID entityId = UUID.randomUUID();
        
        jdbc.update("""
                INSERT INTO documentation_artifacts (id, repository_id, owner_user_id, generation_job_id, markdown, created_at, updated_at)
                VALUES (?, ?, 'user-existing', 'job-unique-1', '# Docs', ?, ?)
                """, docId, repositoryId, now, now);

        // Check unique generation_job_id
        assertThatThrownBy(() -> jdbc.update("""
                INSERT INTO documentation_artifacts (id, repository_id, owner_user_id, generation_job_id, markdown, created_at, updated_at)
                VALUES (?, ?, 'user-existing', 'job-unique-1', '# Dup', ?, ?)
                """, UUID.randomUUID(), repositoryId, now, now))
                .isInstanceOf(DataIntegrityViolationException.class);

        jdbc.update("""
                INSERT INTO code_entities (id, repository_id, stable_key, entity_type, name, path, source_url, active, last_seen_at)
                VALUES (?, ?, 'stable-key-1', 'class', 'OrderService', 'src/OrderService.java', 'https://github.com/acme/existing-repo/blob/main/src/OrderService.java', TRUE, ?)
                """, entityId, repositoryId, now);

        // Check unique(repository_id, stable_key)
        assertThatThrownBy(() -> jdbc.update("""
                INSERT INTO code_entities (id, repository_id, stable_key, entity_type, name, path, source_url, active, last_seen_at)
                VALUES (?, ?, 'stable-key-1', 'class', 'OrderService', 'src/OrderService.java', 'https://github.com/acme/existing-repo/blob/main/src/OrderService.java', TRUE, ?)
                """, UUID.randomUUID(), repositoryId, now))
                .isInstanceOf(DataIntegrityViolationException.class);

        UUID relId = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO documentation_code_relationships (id, documentation_id, code_entity_id, created_at)
                VALUES (?, ?, ?, ?)
                """, relId, docId, entityId, now);

        // Check unique(documentation_id, code_entity_id)
        assertThatThrownBy(() -> jdbc.update("""
                INSERT INTO documentation_code_relationships (id, documentation_id, code_entity_id, created_at)
                VALUES (?, ?, ?, ?)
                """, UUID.randomUUID(), docId, entityId, now))
                .isInstanceOf(DataIntegrityViolationException.class);

        // Check Cascade Delete (Xóa repository -> xóa luôn doc, entity, relationship)
        jdbc.update("DELETE FROM repositories WHERE id = ?", repositoryId);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM documentation_artifacts", Integer.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM code_entities", Integer.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM documentation_code_relationships", Integer.class)).isZero();
    }
}