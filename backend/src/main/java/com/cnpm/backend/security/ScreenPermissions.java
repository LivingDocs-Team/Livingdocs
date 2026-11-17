package com.cnpm.backend.security;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;

/**
 * The Screen Authorization matrix: which actions each role may perform on each screen.
 *
 * <p>This is the backend copy of {@code frontend/src/rbac/permissions.js}. Keep both in step: a test
 * (ScreenPermissionsParityTest) fails when the two tables differ.
 *
 * <p>Actions: C create, R read, U update, D delete (deactivate for accounts), A approve/reject, E export.
 * A role string of the matrix columns is one of {@link #ROLES}; the legacy {@code ADMIN} role is treated as
 * {@code ADMINISTRATOR}.
 */
public final class ScreenPermissions {

    /** Column order of the matrix. */
    public static final List<String> ROLES =
            List.of("DEVELOPER", "STAFF", "MANAGER", "TECHNICAL_LEAD", "ADMINISTRATOR");

    /** screen key -> (role -> actions). */
    private static final Map<String, Map<String, String>> MATRIX = new LinkedHashMap<>();
    /** screen key -> row number of the specification table. */
    private static final Map<String, Integer> ROW_NUMBERS = new LinkedHashMap<>();

    static {
        //   row, screen,                    DEVELOPER, STAFF,  MANAGER, TECH LEAD, ADMIN
        row(1, "authentication",            "R",    "R",    "R",    "R",    "R");
        row(2, "profile",                   "RU",   "RU",   "RU",   "RU",   "RU");
        row(3, "notifications",             "R",    "",     "",     "",     "");
        row(5, "githubConnection",          "CRD",  "",     "",     "",     "");
        row(6, "repositories",              "CRUD", "",     "",     "",     "CRUD");
        row(7, "pullRequests",              "R",    "",     "",     "R",    "");
        row(8, "documentation",             "CRUE", "RU",   "",     "R",    "");
        row(9, "workflowSubmission",        "CR",   "",     "",     "R",    "");
        row(10, "staffReview",              "R",    "CRUA", "R",    "R",    "");
        row(11, "managerApproval",          "",     "",     "RUA",  "R",    "");
        row(12, "approvalPolicies",         "",     "",     "CRU",  "",     "");
        row(13, "approvalAudit",            "",     "R",    "R",    "R",    "R");
        row(17, "driftPolicies",            "",     "",     "",     "CRU",  "");
        row(18, "versionHistory",           "R",    "R",    "",     "R",    "");
        row(19, "documentRollback",         "U",    "",     "U",    "U",    "");
        row(20, "knowledgeBase",            "R",    "",     "",     "R",    "");
        row(22, "templates",                "R",    "R",    "",     "CRUD", "");
        row(23, "healthReports",            "",     "",     "",     "RE",   "");
        row(24, "userManagement",           "",     "",     "",     "",     "CRUD");
        row(25, "workspaceAdministration",  "",     "",     "",     "",     "CRUD");
        row(26, "systemConfiguration",      "",     "",     "",     "",     "CRU");
        row(27, "monitoring",               "",     "",     "",     "",     "R");
        row(28, "notificationPolicies",     "",     "",     "",     "",     "CRU");
    }

    private ScreenPermissions() {
    }

    private static void row(int number, String screen, String developer, String staff, String manager,
            String technicalLead, String administrator) {
        Map<String, String> byRole = new LinkedHashMap<>();
        String[] cells = {developer, staff, manager, technicalLead, administrator};
        for (int i = 0; i < ROLES.size(); i++) {
            byRole.put(ROLES.get(i), cells[i]);
        }
        MATRIX.put(screen, Map.copyOf(byRole));
        ROW_NUMBERS.put(screen, number);
    }

    /** Normalised matrix role for an account role such as {@code STAFF}, {@code ROLE_STAFF} or {@code ADMIN}. */
    public static Optional<String> normalizeRole(String role) {
        if (role == null) return Optional.empty();
        String name = role.trim().toUpperCase(Locale.ROOT);
        if (name.startsWith("ROLE_")) name = name.substring("ROLE_".length());
        if (name.equals("ADMIN")) name = "ADMINISTRATOR";
        return ROLES.contains(name) ? Optional.of(name) : Optional.empty();
    }

    /** True when the role may perform {@code action} on {@code screen}; unknown roles and screens are denied. */
    public static boolean can(String role, String screen, char action) {
        return normalizeRole(role)
                .map(normalized -> actions(screen, normalized).indexOf(action) >= 0)
                .orElse(false);
    }

    /** The action letters a (normalised) role has on a screen; empty when it has none or the screen is unknown. */
    public static String actions(String screen, String normalizedRole) {
        Map<String, String> byRole = MATRIX.get(screen);
        return byRole == null ? "" : byRole.getOrDefault(normalizedRole, "");
    }

    /** Screen keys in row order. */
    public static List<String> screens() {
        return List.copyOf(MATRIX.keySet());
    }

    /** Row number of the specification table, or -1 for an unknown screen. */
    public static int rowNumber(String screen) {
        return ROW_NUMBERS.getOrDefault(screen, -1);
    }
}
