package com.cnpm.backend.security;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

/**
 * The matrix lives twice: frontend/src/rbac/permissions.js (menus, route guard, buttons) and
 * ScreenPermissions (the BFF). This test reads the JavaScript table and fails when the two differ, so a
 * permission cannot be changed in only one place.
 */
class ScreenPermissionsParityTest {

    private static final Pattern ROW = Pattern.compile(
            "^\\s*\\[(\\d+),\\s*'(\\w+)',\\s*'[^']*',\\s*'([A-Z]+)',\\s*((?:FULL|'[A-Z]*')(?:,\\s*(?:FULL|'[A-Z]*')){4})\\],?\\s*$");

    private record JsRow(int number, String screen, Map<String, String> actionsByRole) {
    }

    private static Path frontendFile(String name) {
        Path dir = Path.of("").toAbsolutePath();
        for (int i = 0; i < 4 && dir != null; i++, dir = dir.getParent()) {
            Path candidate = dir.resolve("frontend/src/rbac").resolve(name);
            if (Files.exists(candidate)) return candidate;
        }
        return null;
    }

    private static List<JsRow> readJsRows(Path file) throws IOException {
        List<JsRow> rows = new ArrayList<>();
        for (String line : Files.readAllLines(file, StandardCharsets.UTF_8)) {
            Matcher m = ROW.matcher(line);
            if (!m.matches()) continue;
            String typical = m.group(3);
            String[] cells = m.group(4).split(",\\s*");
            Map<String, String> byRole = new LinkedHashMap<>();
            for (int i = 0; i < ScreenPermissions.ROLES.size(); i++) {
                String cell = cells[i].trim();
                byRole.put(ScreenPermissions.ROLES.get(i),
                        cell.equals("FULL") ? typical : cell.substring(1, cell.length() - 1));
            }
            rows.add(new JsRow(Integer.parseInt(m.group(1)), m.group(2), byRole));
        }
        return rows;
    }

    @Test
    void javaMatrixEqualsTheFrontendMatrix() throws IOException {
        Path file = frontendFile("permissions.js");
        assumeTrue(file != null, "frontend sources are not next to the backend (for example a Docker build context)");

        List<JsRow> jsRows = readJsRows(file);
        assertThat(jsRows).as("rows parsed from permissions.js").isNotEmpty();

        assertThat(ScreenPermissions.screens())
                .as("screen keys, in row order")
                .containsExactlyElementsOf(jsRows.stream().map(JsRow::screen).toList());
        for (JsRow row : jsRows) {
            assertThat(ScreenPermissions.rowNumber(row.screen()))
                    .as("row number of " + row.screen()).isEqualTo(row.number());
            for (String role : ScreenPermissions.ROLES) {
                assertThat(ScreenPermissions.actions(row.screen(), role))
                        .as(row.screen() + " / " + role)
                        .isEqualTo(row.actionsByRole().get(role));
            }
        }
    }

    @Test
    void javaRolesEqualTheFrontendRoles() throws IOException {
        Path file = frontendFile("roles.js");
        assumeTrue(file != null, "frontend sources are not next to the backend (for example a Docker build context)");

        List<String> jsRoles = new ArrayList<>();
        boolean inLabels = false;
        for (String line : Files.readAllLines(file, StandardCharsets.UTF_8)) {
            if (line.contains("ROLE_LABELS = Object.freeze({")) {
                inLabels = true;
            } else if (inLabels && line.contains("})")) {
                break;
            } else if (inLabels) {
                Matcher m = Pattern.compile("^\\s*(\\w+):\\s*'").matcher(line);
                if (m.find()) jsRoles.add(m.group(1));
            }
        }
        assertThat(ScreenPermissions.ROLES).containsExactlyElementsOf(jsRoles);
    }

    @Test
    void roleSpellingsAndLegacyAdminAreNormalised() {
        assertThat(ScreenPermissions.normalizeRole("staff")).contains("STAFF");
        assertThat(ScreenPermissions.normalizeRole(" ROLE_MANAGER ")).contains("MANAGER");
        assertThat(ScreenPermissions.normalizeRole("ADMIN")).contains("ADMINISTRATOR");
        assertThat(ScreenPermissions.normalizeRole("GUEST")).isEmpty();
        assertThat(ScreenPermissions.normalizeRole("")).isEmpty();
        assertThat(ScreenPermissions.normalizeRole(null)).isEmpty();
        assertThat(ScreenPermissions.can("ADMIN", "userManagement", 'D')).isTrue();
        assertThat(ScreenPermissions.can("DEVELOPER", "userManagement", 'R')).isFalse();
        assertThat(ScreenPermissions.can("DEVELOPER", "noSuchScreen", 'R')).isFalse();
        assertThat(ScreenPermissions.can(null, "profile", 'R')).isFalse();
    }
}
