package com.livingdocs.github.config;

import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.Test;
import org.flywaydb.core.Flyway;

import javax.sql.DataSource;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.zip.CRC32;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class FlywayMigrationLineageSelectorTest {

    private final FlywayMigrationLineageSelector selector = new FlywayMigrationLineageSelector();

    @Test
    void selectsCurrentLineageForAnEmptyDatabase() {
        assertThat(selector.select(dataSource())).isEqualTo(
                FlywayMigrationLineageSelector.Lineage.CURRENT);
    }

    @Test
    void selectsLegacyOnlyForTheKnownAppliedRelationshipsV2ScriptAndChecksum() throws Exception {
        DataSource dataSource = dataSource();
        createHistory(dataSource);
        createLegacyRelationshipTables(dataSource);
        insertHistory(dataSource, "1", "V1__init_github_integration.sql", 93_468_710, true);
        insertHistory(dataSource, "2", "V2__documentation_code_relationships.sql",
                FlywayMigrationLineageSelector.LEGACY_V2_CHECKSUM, true);

        assertThat(selector.select(dataSource)).isEqualTo(
                FlywayMigrationLineageSelector.Lineage.LEGACY_RELATIONSHIPS_V2);
    }

    @Test
    void selectsCurrentLineageForTheCurrentWorkflowV2ScriptAndChecksum() throws Exception {
        DataSource dataSource = dataSource();
        createHistory(dataSource);
        insertHistory(dataSource, "1", "V1__init_github_integration.sql", 93_468_710, true);
        insertHistory(dataSource, "2", "V2__document_review_workflow.sql",
                FlywayMigrationLineageSelector.CURRENT_V2_CHECKSUM, true);

        assertThat(selector.select(dataSource)).isEqualTo(
                FlywayMigrationLineageSelector.Lineage.CURRENT);
    }

    @Test
    void choosesOneCanonicalV5ForAnEmptyDatabaseAndCreatesBothFeatureSchemas() throws Exception {
        DataSource dataSource = dataSource();
        Flyway flyway = Flyway.configure().dataSource(dataSource)
                .locations(selector.select(dataSource).location()).load();

        flyway.migrate();
        flyway.validate();

        assertThat(flyway.info().applied()).extracting(migration -> migration.getScript())
                .contains("V5__documentation_code_relationships_and_pull_requests.sql");
        assertThat(tableNames(dataSource)).contains("documentation_artifacts", "code_entities",
                "documentation_code_relationships", "github_commits", "github_pull_requests",
                "document_workflows", "document_workflow_audit", "source_changes",
                "source_change_files", "source_change_entities");
    }

    @Test
    void validatesAndAdvancesDatabaseThatAlreadyAppliedDocumentationV5() throws Exception {
        DataSource dataSource = dataSource();
        Flyway original = Flyway.configure().dataSource(dataSource)
                .locations("classpath:db/migration-current-documents-v5")
                .target("5").load();
        original.migrate();
        int originalChecksum = appliedChecksum(original, "5");

        assertThat(selector.select(dataSource)).isEqualTo(
                FlywayMigrationLineageSelector.Lineage.CURRENT_DOCUMENTATION_V5);
        Flyway compatible = Flyway.configure().dataSource(dataSource)
                .locations(selector.select(dataSource).location()).load();
        compatible.migrate();
        compatible.validate();

        assertThat(appliedChecksum(compatible, "5")).isEqualTo(originalChecksum);
        assertThat(compatible.info().applied()).extracting(migration -> migration.getVersion().getVersion())
                .contains("6", "7");
        assertThat(tableNames(dataSource)).contains("documentation_code_relationships", "github_pull_requests",
                "source_changes", "source_change_files", "source_change_entities");
    }

    @Test
    void validatesAndAdvancesDatabaseThatAlreadyAppliedPullRequestsV5() throws Exception {
        DataSource dataSource = dataSource();
        Flyway original = Flyway.configure().dataSource(dataSource)
                .locations("classpath:db/migration-current-pull-requests-v5")
                .target("5").load();
        original.migrate();
        int originalChecksum = appliedChecksum(original, "5");

        assertThat(selector.select(dataSource)).isEqualTo(
                FlywayMigrationLineageSelector.Lineage.CURRENT_PULL_REQUESTS_V5);
        Flyway compatible = Flyway.configure().dataSource(dataSource)
                .locations(selector.select(dataSource).location()).load();
        compatible.migrate();
        compatible.validate();

        assertThat(appliedChecksum(compatible, "5")).isEqualTo(originalChecksum);
        assertThat(compatible.info().applied()).extracting(migration -> migration.getVersion().getVersion())
                .contains("6", "7");
        assertThat(tableNames(dataSource)).contains("documentation_code_relationships", "github_pull_requests",
                "source_changes", "source_change_files", "source_change_entities");
    }

    @Test
    void preservesDocumentationV5AndSourceChangesV6HistoryAndAddsPullRequestsAtV7() throws Exception {
        assertThatExistingV6SourceChangesHistoryIsPreserved(
                "classpath:db/migration-current-documents-v5-source-changes-v6",
                FlywayMigrationLineageSelector.Lineage.CURRENT_DOCUMENTATION_V5_SOURCE_CHANGES_V6,
                "V7__pull_requests_and_commits.sql");
    }

    @Test
    void preservesPullRequestsV5AndSourceChangesV6HistoryAndAddsDocumentationAtV7() throws Exception {
        assertThatExistingV6SourceChangesHistoryIsPreserved(
                "classpath:db/migration-current-pull-requests-v5-source-changes-v6",
                FlywayMigrationLineageSelector.Lineage.CURRENT_PULL_REQUESTS_V5_SOURCE_CHANGES_V6,
                "V7__documentation_code_relationships.sql");
    }

    private void assertThatExistingV6SourceChangesHistoryIsPreserved(String originalLocation,
            FlywayMigrationLineageSelector.Lineage expectedLineage, String expectedV7Script) throws Exception {
        DataSource dataSource = dataSource();
        Flyway original = Flyway.configure().dataSource(dataSource)
                .locations(originalLocation).target("6").load();
        original.migrate();
        int originalChecksum = appliedChecksum(original, "6");

        assertThat(selector.select(dataSource)).isEqualTo(expectedLineage);
        Flyway compatible = Flyway.configure().dataSource(dataSource)
                .locations(selector.select(dataSource).location()).load();
        compatible.migrate();
        compatible.validate();

        assertThat(appliedChecksum(compatible, "6")).isEqualTo(originalChecksum);
        assertThat(compatible.info().applied()).extracting(migration -> migration.getScript())
                .contains(expectedV7Script);
        assertThat(tableNames(dataSource)).contains("source_changes", "source_change_files",
                "source_change_entities", "documentation_code_relationships", "github_pull_requests");
    }

    @Test
    void legacyV2RelationshipsKeepDataAndAdvanceWithNonconflictingV5() throws Exception {
        DataSource dataSource = dataSource();
        Flyway original = Flyway.configure().dataSource(dataSource)
                .locations(FlywayMigrationLineageSelector.LEGACY_LOCATION)
                .target("4").load();
        original.migrate();
        int legacyChecksum = appliedChecksum(original, "2");
        insertLegacyRelationship(dataSource);

        assertThat(selector.select(dataSource)).isEqualTo(
                FlywayMigrationLineageSelector.Lineage.LEGACY_RELATIONSHIPS_V2);
        Flyway compatible = Flyway.configure().dataSource(dataSource)
                .locations(selector.select(dataSource).location()).load();
        compatible.migrate();
        compatible.validate();

        assertThat(appliedChecksum(compatible, "2")).isEqualTo(legacyChecksum);
        assertThat(relationshipCount(dataSource)).isEqualTo(1);
        assertThat(tableNames(dataSource)).contains("github_commits", "github_pull_requests", "source_changes",
                "source_change_files", "source_change_entities");
    }

    @Test
    void rejectsAnUnknownV2ChecksumInsteadOfWeakeningValidation() throws Exception {
        DataSource dataSource = dataSource();
        createHistory(dataSource);
        insertHistory(dataSource, "1", "V1__init_github_integration.sql", 93_468_710, true);
        insertHistory(dataSource, "2", "V2__documentation_code_relationships.sql", 12345, true);

        assertThatThrownBy(() -> selector.select(dataSource))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("Unsupported Flyway V2 history")
                .hasMessageContaining("refusing to skip validation");
    }

    @Test
    void rejectsLegacyHistoryWhenRelationshipTablesAreMissing() throws Exception {
        DataSource dataSource = dataSource();
        createHistory(dataSource);
        insertHistory(dataSource, "1", "V1__init_github_integration.sql", 93_468_710, true);
        insertHistory(dataSource, "2", "V2__documentation_code_relationships.sql",
                FlywayMigrationLineageSelector.LEGACY_V2_CHECKSUM, true);

        assertThatThrownBy(() -> selector.select(dataSource))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("relationship tables are incomplete");
    }

    @Test
    void rejectsAHistoryContainingFailedMigrations() throws Exception {
        DataSource dataSource = dataSource();
        createHistory(dataSource);
        insertHistory(dataSource, "1", "V1__init_github_integration.sql", 93_468_710, false);

        assertThatThrownBy(() -> selector.select(dataSource))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("contains a failed migration");
    }

    @Test
    void rejectsApplicationTablesWithoutFlywayHistory() throws Exception {
        DataSource dataSource = dataSource();
        try (Connection connection = dataSource.getConnection();
             Statement statement = connection.createStatement()) {
            statement.execute("CREATE TABLE repositories (id INTEGER PRIMARY KEY)");
        }

        assertThatThrownBy(() -> selector.select(dataSource))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("application tables without Flyway history");
    }

    @Test
    void legacyMigrationResourcesPreserveAppliedChecksumsAndSharedMigrations() throws Exception {
        assertThat(resourceChecksum("db/migration-legacy/V2__documentation_code_relationships.sql"))
                .isEqualTo(FlywayMigrationLineageSelector.LEGACY_V2_CHECKSUM);
        assertThat(resourceChecksum("db/migration/V2__document_review_workflow.sql"))
                .isEqualTo(FlywayMigrationLineageSelector.CURRENT_V2_CHECKSUM);

        for (String name : new String[] {
                "V1__init_github_integration.sql",
                "V2_1__ensure_document_workflow_tables.sql",
                "V3__document_workflow_reviewer_audit.sql",
                "V4__document_workflow_audit_actor_role.sql"}) {
            assertThat(resourceBytes("db/migration-legacy/" + name))
                    .as("legacy and current migration contents for %s", name)
                    .isEqualTo(resourceBytes("db/migration/" + name));
            assertThat(resourceBytes("db/migration-current/" + name))
                    .as("current migration contents for %s", name)
                    .isEqualTo(resourceBytes("db/migration/" + name));
        }
        assertThat(resourceBytes("db/migration-current-documents-v5/V5__documentation_code_relationships.sql"))
                .isEqualTo(resourceBytes("db/migration/V5__documentation_code_relationships.sql"));
        assertThat(resourceBytes("db/migration-current-pull-requests-v5/V5__pull_requests_and_commits.sql"))
                .isEqualTo(resourceBytes("db/migration-legacy/V5__pull_requests_and_commits.sql"));
        for (String resource : new String[] {
                "db/migration-legacy/V6__source_changes.sql",
                "db/migration-current/V6__source_changes.sql",
                "db/migration-current-documents-v5/V7__source_changes.sql",
                "db/migration-current-pull-requests-v5/V7__source_changes.sql",
                "db/migration-current-documents-v5-source-changes-v6/V6__source_changes.sql",
                "db/migration-current-pull-requests-v5-source-changes-v6/V6__source_changes.sql"}) {
            assertThat(resourceBytes(resource))
                    .as("preserve the source changes V6 migration byte-for-byte at %s", resource)
                    .isEqualTo(resourceBytes("db/migration-current/V6__source_changes.sql"));
        }
        assertThat(resourceBytes(
                "db/migration-current-documents-v5-source-changes-v6/V7__pull_requests_and_commits.sql"))
                .isEqualTo(resourceBytes("db/migration-current-documents-v5/V6__pull_requests_and_commits.sql"));
        assertThat(resourceBytes(
                "db/migration-current-pull-requests-v5-source-changes-v6/V7__documentation_code_relationships.sql"))
                .isEqualTo(resourceBytes("db/migration-current-pull-requests-v5/V6__documentation_code_relationships.sql"));
    }

    private DataSource dataSource() {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:lineage" + System.nanoTime() + ";DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");
        return dataSource;
    }

    private void createHistory(DataSource dataSource) throws Exception {
        try (Connection connection = dataSource.getConnection();
             Statement statement = connection.createStatement()) {
            statement.execute("CREATE TABLE flyway_schema_history (installed_rank INTEGER, "
                    + "version VARCHAR(50), script VARCHAR(255), checksum INTEGER, success BOOLEAN)");
        }
    }

    private void createLegacyRelationshipTables(DataSource dataSource) throws Exception {
        try (Connection connection = dataSource.getConnection();
             Statement statement = connection.createStatement()) {
            statement.execute("CREATE TABLE documentation_artifacts (id INTEGER PRIMARY KEY)");
            statement.execute("CREATE TABLE code_entities (id INTEGER PRIMARY KEY)");
            statement.execute("CREATE TABLE documentation_code_relationships (id INTEGER PRIMARY KEY)");
        }
    }

    private void insertHistory(DataSource dataSource, String version, String script,
            int checksum, boolean success) throws Exception {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     "INSERT INTO flyway_schema_history(installed_rank, version, script, checksum, success) "
                             + "VALUES ((SELECT COALESCE(MAX(installed_rank), 0) + 1 "
                             + "FROM flyway_schema_history), ?, ?, ?, ?)")) {
            statement.setString(1, version);
            statement.setString(2, script);
            statement.setInt(3, checksum);
            statement.setBoolean(4, success);
            statement.executeUpdate();
        }
    }

    private int resourceChecksum(String resource) throws IOException {
        CRC32 checksum = new CRC32();
        try (InputStream stream = resourceStream(resource);
             BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                checksum.update(line.getBytes(StandardCharsets.UTF_8));
            }
        }
        return (int) checksum.getValue();
    }

    private int appliedChecksum(Flyway flyway, String version) {
        return java.util.Arrays.stream(flyway.info().applied())
                .filter(migration -> migration.getVersion().getVersion().equals(version))
                .findFirst().orElseThrow().getChecksum();
    }

    private java.util.Set<String> tableNames(DataSource dataSource) throws Exception {
        java.util.Set<String> names = new java.util.HashSet<>();
        try (Connection connection = dataSource.getConnection();
             ResultSet tables = connection.getMetaData().getTables(null, null, "%", new String[] {"TABLE"})) {
            while (tables.next()) names.add(tables.getString("TABLE_NAME").toLowerCase());
        }
        return names;
    }

    private void insertLegacyRelationship(DataSource dataSource) throws Exception {
        try (Connection connection = dataSource.getConnection(); Statement statement = connection.createStatement()) {
            statement.execute("INSERT INTO github_connections (id, user_id, github_user_id, github_login, status, "
                    + "created_at, updated_at) VALUES ('11111111-1111-4111-8111-111111111111', 'u', 1, 'u', "
                    + "'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)");
            statement.execute("INSERT INTO repositories (id, workspace_id, connection_id, github_repo_id, full_name, "
                    + "status, created_at) VALUES ('22222222-2222-4222-8222-222222222222', 'w', "
                    + "'11111111-1111-4111-8111-111111111111', 1, 'o/r', 'CONNECTED', CURRENT_TIMESTAMP)");
            statement.execute("INSERT INTO documentation_artifacts (id, repository_id, owner_user_id, "
                    + "generation_job_id, created_at, updated_at) VALUES ('33333333-3333-4333-8333-333333333333', "
                    + "'22222222-2222-4222-8222-222222222222', 'u', 'job', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)");
            statement.execute("INSERT INTO code_entities (id, repository_id, stable_key, entity_type, name, path, "
                    + "source_url, active, last_seen_at) VALUES ('44444444-4444-4444-8444-444444444444', "
                    + "'22222222-2222-4222-8222-222222222222', 'key', 'function', 'name', 'src/a.py', 'https://example.test', "
                    + "TRUE, CURRENT_TIMESTAMP)");
            statement.execute("INSERT INTO documentation_code_relationships (id, documentation_id, code_entity_id, "
                    + "created_at) VALUES ('55555555-5555-4555-8555-555555555555', "
                    + "'33333333-3333-4333-8333-333333333333', '44444444-4444-4444-8444-444444444444', CURRENT_TIMESTAMP)");
        }
    }

    private int relationshipCount(DataSource dataSource) throws Exception {
        try (Connection connection = dataSource.getConnection(); Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery("SELECT COUNT(*) FROM documentation_code_relationships")) {
            result.next();
            return result.getInt(1);
        }
    }

    private byte[] resourceBytes(String resource) throws IOException {
        try (InputStream stream = resourceStream(resource)) {
            return stream.readAllBytes();
        }
    }

    private InputStream resourceStream(String resource) {
        InputStream stream = getClass().getClassLoader().getResourceAsStream(resource);
        if (stream == null) throw new IllegalStateException("Missing migration resource: " + resource);
        return stream;
    }
}
