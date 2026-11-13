package com.livingdocs.github.config;

import org.springframework.stereotype.Component;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Selects the migration history that exactly matches a database's recorded V2 lineage. */
@Component
public class FlywayMigrationLineageSelector {

    public static final String CURRENT_LOCATION = "classpath:db/migration-current";
    public static final String LEGACY_LOCATION = "classpath:db/migration-legacy";
    public static final String CURRENT_DOCUMENTATION_V5_LOCATION = "classpath:db/migration-current-documents-v5";
    public static final String CURRENT_PULL_REQUESTS_V5_LOCATION = "classpath:db/migration-current-pull-requests-v5";
    public static final String CURRENT_DOCUMENTATION_V5_SOURCE_CHANGES_V6_LOCATION =
            "classpath:db/migration-current-documents-v5-source-changes-v6";
    public static final String CURRENT_PULL_REQUESTS_V5_SOURCE_CHANGES_V6_LOCATION =
            "classpath:db/migration-current-pull-requests-v5-source-changes-v6";

    static final String LEGACY_V2_SCRIPT = "V2__documentation_code_relationships.sql";
    static final int LEGACY_V2_CHECKSUM = -1_628_419_878;
    static final String CURRENT_V2_SCRIPT = "V2__document_review_workflow.sql";
    static final int CURRENT_V2_CHECKSUM = 132_858_761;
    private static final String DOCUMENTATION_V5_SCRIPT = "V5__documentation_code_relationships.sql";
    private static final String PULL_REQUESTS_V5_SCRIPT = "V5__pull_requests_and_commits.sql";
    private static final String COMBINED_V5_SCRIPT = "V5__documentation_code_relationships_and_pull_requests.sql";
    private static final String SOURCE_CHANGES_V6_SCRIPT = "V6__source_changes.sql";
    private static final String PULL_REQUESTS_V6_SCRIPT = "V6__pull_requests_and_commits.sql";
    private static final String DOCUMENTATION_V6_SCRIPT = "V6__documentation_code_relationships.sql";
    private static final String V1_SCRIPT = "V1__init_github_integration.sql";
    private static final Set<String> REQUIRED_LEGACY_RELATIONSHIP_TABLES = Set.of(
            "documentation_artifacts", "code_entities", "documentation_code_relationships");

    public Lineage select(DataSource dataSource) {
        try (Connection connection = dataSource.getConnection()) {
            Set<String> tables = publicTableNames(connection);
            if (!tables.contains("flyway_schema_history")) {
                if (!tables.isEmpty()) {
                    throw new IllegalStateException("Database contains application tables without "
                            + "Flyway history; refusing to choose a migration lineage.");
                }
                return Lineage.CURRENT;
            }

            List<HistoryEntry> history = readHistory(connection);
            if (history.isEmpty()) {
                if (tables.size() > 1) {
                    throw new IllegalStateException("Flyway history is empty but application tables exist; "
                            + "refusing to choose a migration lineage.");
                }
                return Lineage.CURRENT;
            }
            if (history.stream().anyMatch(entry -> !entry.success())) {
                throw new IllegalStateException("Flyway history contains a failed migration; "
                        + "refusing to choose a migration lineage.");
            }

            HistoryEntry v1 = history.stream().filter(entry -> "1".equals(entry.version())
                    && V1_SCRIPT.equals(entry.script())).findFirst().orElse(null);
            if (v1 == null) {
                throw new IllegalStateException("Flyway history does not contain the expected V1 migration; "
                        + "refusing to choose a migration lineage.");
            }

            HistoryEntry v2 = history.stream().filter(entry -> "2".equals(entry.version()))
                    .findFirst().orElse(null);
            if (v2 == null) {
                if (history.stream().anyMatch(entry -> !"1".equals(entry.version()))) {
                    throw new IllegalStateException("Flyway history has an unsupported migration sequence; "
                            + "refusing to choose a migration lineage.");
                }
                return Lineage.CURRENT;
            }

            if (LEGACY_V2_SCRIPT.equals(v2.script())
                    && Integer.valueOf(LEGACY_V2_CHECKSUM).equals(v2.checksum())) {
                if (!tables.containsAll(REQUIRED_LEGACY_RELATIONSHIP_TABLES)) {
                    throw new IllegalStateException("Legacy V2 history is present, but its documentation/code "
                            + "relationship tables are incomplete; refusing to choose a migration lineage.");
                }
                HistoryEntry v5 = history.stream().filter(entry -> "5".equals(entry.version()))
                        .findFirst().orElse(null);
                if (v5 != null && !PULL_REQUESTS_V5_SCRIPT.equals(v5.script())) {
                    throw new IllegalStateException("Legacy V2 history records an unsupported V5 migration; "
                            + "refusing to choose a migration lineage.");
                }
                HistoryEntry v6 = history.stream().filter(entry -> "6".equals(entry.version()))
                        .findFirst().orElse(null);
                if (v6 != null && !SOURCE_CHANGES_V6_SCRIPT.equals(v6.script())) {
                    throw new IllegalStateException("Legacy V2 history records an unsupported V6 migration; "
                            + "refusing to choose a migration lineage.");
                }
                return Lineage.LEGACY_RELATIONSHIPS_V2;
            }

            if (CURRENT_V2_SCRIPT.equals(v2.script())
                    && Integer.valueOf(CURRENT_V2_CHECKSUM).equals(v2.checksum())) {
                HistoryEntry v5 = history.stream().filter(entry -> "5".equals(entry.version()))
                        .findFirst().orElse(null);
                HistoryEntry v6 = history.stream().filter(entry -> "6".equals(entry.version()))
                        .findFirst().orElse(null);
                if (v5 == null || COMBINED_V5_SCRIPT.equals(v5.script())) {
                    if (v6 != null && !SOURCE_CHANGES_V6_SCRIPT.equals(v6.script())) {
                        throw new IllegalStateException("Current V2 history records an unsupported V6 migration; "
                                + "refusing to choose a migration lineage.");
                    }
                    return Lineage.CURRENT;
                }
                if (DOCUMENTATION_V5_SCRIPT.equals(v5.script())) {
                    if (SOURCE_CHANGES_V6_SCRIPT.equals(v6 == null ? null : v6.script())) {
                        return Lineage.CURRENT_DOCUMENTATION_V5_SOURCE_CHANGES_V6;
                    }
                    if (v6 != null && !PULL_REQUESTS_V6_SCRIPT.equals(v6.script())) {
                        throw new IllegalStateException("Current V2 history records an unsupported V6 migration; "
                                + "refusing to choose a migration lineage.");
                    }
                    return Lineage.CURRENT_DOCUMENTATION_V5;
                }
                if (PULL_REQUESTS_V5_SCRIPT.equals(v5.script())) {
                    if (SOURCE_CHANGES_V6_SCRIPT.equals(v6 == null ? null : v6.script())) {
                        return Lineage.CURRENT_PULL_REQUESTS_V5_SOURCE_CHANGES_V6;
                    }
                    if (v6 != null && !DOCUMENTATION_V6_SCRIPT.equals(v6.script())) {
                        throw new IllegalStateException("Current V2 history records an unsupported V6 migration; "
                                + "refusing to choose a migration lineage.");
                    }
                    return Lineage.CURRENT_PULL_REQUESTS_V5;
                }
                throw new IllegalStateException("Current V2 history records an unsupported V5 migration; "
                        + "refusing to choose a migration lineage.");
            }

            throw new IllegalStateException("Unsupported Flyway V2 history (script=" + v2.script()
                    + ", checksum=" + v2.checksum() + "); refusing to skip validation or alter history.");
        } catch (SQLException exception) {
            throw new IllegalStateException("Could not inspect Flyway history before migration; "
                    + "refusing to choose a migration lineage.", exception);
        }
    }

    private Set<String> publicTableNames(Connection connection) throws SQLException {
        Set<String> names = new HashSet<>();
        try (ResultSet tables = connection.getMetaData().getTables(
                connection.getCatalog(), null, "%", new String[] {"TABLE"})) {
            while (tables.next()) {
                String schema = tables.getString("TABLE_SCHEM");
                if (schema == null || "public".equalsIgnoreCase(schema)
                        || "PUBLIC".equalsIgnoreCase(schema)) {
                    names.add(tables.getString("TABLE_NAME").toLowerCase(Locale.ROOT));
                }
            }
        }
        return names;
    }

    private List<HistoryEntry> readHistory(Connection connection) throws SQLException {
        List<HistoryEntry> entries = new ArrayList<>();
        DatabaseMetaData metadata = connection.getMetaData();
        String tableName = findTableName(metadata, connection, "flyway_schema_history");
        if (tableName == null) {
            throw new IllegalStateException("Flyway history table disappeared during lineage inspection.");
        }
        String version = findColumnName(metadata, connection, tableName, "version");
        String script = findColumnName(metadata, connection, tableName, "script");
        String checksumColumn = findColumnName(metadata, connection, tableName, "checksum");
        String success = findColumnName(metadata, connection, tableName, "success");
        String installedRank = findColumnName(metadata, connection, tableName, "installed_rank");
        String sql = "SELECT " + quote(metadata, version) + ", " + quote(metadata, script) + ", "
                + quote(metadata, checksumColumn) + ", " + quote(metadata, success) + " FROM "
                + quote(metadata, tableName) + " ORDER BY " + quote(metadata, installedRank);
        try (Statement statement = connection.createStatement();
             ResultSet rows = statement.executeQuery(sql)) {
            while (rows.next()) {
                int checksum = rows.getInt("checksum");
                Integer nullableChecksum = rows.wasNull() ? null : checksum;
                entries.add(new HistoryEntry(rows.getString("version"), rows.getString("script"),
                        nullableChecksum, rows.getBoolean("success")));
            }
        }
        return entries;
    }

    private String findTableName(DatabaseMetaData metadata, Connection connection, String expected)
            throws SQLException {
        try (ResultSet tables = metadata.getTables(connection.getCatalog(), null, "%", new String[] {"TABLE"})) {
            while (tables.next()) {
                String tableName = tables.getString("TABLE_NAME");
                String schema = tables.getString("TABLE_SCHEM");
                if (expected.equalsIgnoreCase(tableName) && (schema == null || "public".equalsIgnoreCase(schema))) {
                    return tableName;
                }
            }
        }
        return null;
    }

    private String findColumnName(DatabaseMetaData metadata, Connection connection, String tableName, String expected)
            throws SQLException {
        try (ResultSet columns = metadata.getColumns(connection.getCatalog(), null, tableName, "%")) {
            while (columns.next()) {
                String columnName = columns.getString("COLUMN_NAME");
                if (expected.equalsIgnoreCase(columnName)) return columnName;
            }
        }
        throw new IllegalStateException("Flyway history table is missing expected column " + expected + ".");
    }

    private String quote(DatabaseMetaData metadata, String identifier) throws SQLException {
        String quote = metadata.getIdentifierQuoteString().trim();
        if (quote.isEmpty()) return identifier;
        return quote + identifier.replace(quote, quote + quote) + quote;
    }

    public enum Lineage {
        CURRENT(CURRENT_LOCATION),
        LEGACY_RELATIONSHIPS_V2(LEGACY_LOCATION),
        CURRENT_DOCUMENTATION_V5(CURRENT_DOCUMENTATION_V5_LOCATION),
        CURRENT_PULL_REQUESTS_V5(CURRENT_PULL_REQUESTS_V5_LOCATION),
        CURRENT_DOCUMENTATION_V5_SOURCE_CHANGES_V6(CURRENT_DOCUMENTATION_V5_SOURCE_CHANGES_V6_LOCATION),
        CURRENT_PULL_REQUESTS_V5_SOURCE_CHANGES_V6(CURRENT_PULL_REQUESTS_V5_SOURCE_CHANGES_V6_LOCATION);

        private final String location;

        Lineage(String location) {
            this.location = location;
        }

        public String location() {
            return location;
        }
    }

    private record HistoryEntry(String version, String script, Integer checksum, boolean success) {
    }
}
