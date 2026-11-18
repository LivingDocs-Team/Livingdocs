package com.cnpm.backend.security;

import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

import static org.assertj.core.api.Assertions.assertThat;

class ApiRoutePermissionsTest {

    private static final String ID = "11111111-1111-4111-8111-111111111111";
    private static final String WS = "ws-42";

    /** route -> roles that may use it, written from the matrix (not computed from the rules). */
    private static final Map<String, List<String>> ALLOWED = Map.ofEntries(
            // GitHub connection (#5) and repositories (#6)
            Map.entry("GET /api/github/authorize-url", List.of("DEVELOPER")),
            Map.entry("GET /api/github/callback", List.of("DEVELOPER")),
            Map.entry("GET /api/github/connection", List.of("DEVELOPER", "ADMINISTRATOR")),
            Map.entry("DELETE /api/github/connection", List.of("DEVELOPER")),
            Map.entry("GET /api/github/repos/available", List.of("DEVELOPER", "ADMINISTRATOR")),
            Map.entry("GET /api/workspaces/" + WS + "/repositories",
                    List.of("DEVELOPER", "STAFF", "TECHNICAL_LEAD", "ADMINISTRATOR")),
            Map.entry("POST /api/workspaces/" + WS + "/repositories", List.of("DEVELOPER", "ADMINISTRATOR")),
            Map.entry("PUT /api/workspaces/" + WS + "/repositories/" + ID, List.of("DEVELOPER", "ADMINISTRATOR")),
            Map.entry("DELETE /api/workspaces/" + WS + "/repositories/" + ID, List.of("DEVELOPER", "ADMINISTRATOR")),
            Map.entry("GET /api/repositories/" + ID, List.of("DEVELOPER", "STAFF", "TECHNICAL_LEAD", "ADMINISTRATOR")),
            Map.entry("DELETE /api/repositories/" + ID, List.of("DEVELOPER", "ADMINISTRATOR")),
            Map.entry("POST /api/repositories/" + ID + "/sync", List.of("DEVELOPER", "ADMINISTRATOR")),
            Map.entry("GET /api/repositories/" + ID + "/sync/latest", List.of("DEVELOPER", "ADMINISTRATOR")),
            // pull requests, commits, source changes (#7)
            Map.entry("GET /api/repositories/" + ID + "/pull-requests", List.of("DEVELOPER", "TECHNICAL_LEAD")),
            Map.entry("GET /api/repositories/" + ID + "/commits", List.of("DEVELOPER", "TECHNICAL_LEAD")),
            Map.entry("GET /api/repositories/" + ID + "/source-changes", List.of("DEVELOPER", "TECHNICAL_LEAD")),
            Map.entry("POST /api/repositories/" + ID + "/source-changes/" + ID + "/retry",
                    List.of("DEVELOPER", "ADMINISTRATOR")),
            // documentation (#8) and knowledge base (#20)
            Map.entry("POST /api/repositories/" + ID + "/documentation/generate", List.of("DEVELOPER")),
            Map.entry("GET /api/documentation/jobs/job-1", List.of("DEVELOPER", "STAFF", "TECHNICAL_LEAD")),
            Map.entry("GET /api/documentation/jobs/job-1/result", List.of("DEVELOPER", "STAFF", "TECHNICAL_LEAD")),
            Map.entry("POST /api/documentation/jobs/job-1/document", List.of("DEVELOPER")),
            Map.entry("GET /api/repositories/" + ID + "/documentation",
                    List.of("DEVELOPER", "STAFF", "TECHNICAL_LEAD")),
            Map.entry("GET /api/repositories/" + ID + "/documentation/search", List.of("DEVELOPER", "TECHNICAL_LEAD")),
            Map.entry("GET /api/documentation/" + ID, List.of("DEVELOPER", "STAFF", "TECHNICAL_LEAD")),
            Map.entry("GET /api/documentation/" + ID + "/code-entities", List.of("DEVELOPER", "STAFF", "TECHNICAL_LEAD")),
            Map.entry("PUT /api/documentation/" + ID + "/code-entities", List.of("DEVELOPER", "STAFF")),
            // templates (#22)
            Map.entry("GET /api/documentation/templates", List.of("DEVELOPER", "STAFF", "TECHNICAL_LEAD")),
            Map.entry("POST /api/documentation/templates", List.of("TECHNICAL_LEAD")),
            Map.entry("PUT /api/documentation/templates/abc", List.of("TECHNICAL_LEAD")),
            Map.entry("DELETE /api/documentation/templates/abc", List.of("TECHNICAL_LEAD")),
            // drift: analysis was removed for every role, thresholds stay for Technical Lead
            Map.entry("GET /api/documentation/drift/severity-rules", List.of("TECHNICAL_LEAD")),
            Map.entry("POST /api/repositories/" + ID + "/drift/analyze", List.of()),
            Map.entry("GET /api/repositories/" + ID + "/drift/reports", List.of()),
            // workflow (#9, #10, #11, #13, #19)
            Map.entry("POST /api/document-workflows", List.of("DEVELOPER")),
            Map.entry("GET /api/document-workflows/mine", List.of("DEVELOPER", "TECHNICAL_LEAD")),
            Map.entry("GET /api/document-workflows/staff/queue",
                    List.of("DEVELOPER", "STAFF", "MANAGER", "TECHNICAL_LEAD")),
            Map.entry("GET /api/document-workflows/manager/queue", List.of("MANAGER", "TECHNICAL_LEAD")),
            Map.entry("GET /api/document-workflows/history-accessible",
                    List.of("DEVELOPER", "STAFF", "MANAGER", "TECHNICAL_LEAD", "ADMINISTRATOR")),
            Map.entry("GET /api/document-workflows/" + ID,
                    List.of("DEVELOPER", "STAFF", "MANAGER", "TECHNICAL_LEAD", "ADMINISTRATOR")),
            Map.entry("GET /api/document-workflows/" + ID + "/history",
                    List.of("DEVELOPER", "STAFF", "MANAGER", "TECHNICAL_LEAD", "ADMINISTRATOR")),
            Map.entry("GET /api/document-workflows/" + ID + "/comments",
                    List.of("DEVELOPER", "STAFF", "MANAGER", "TECHNICAL_LEAD", "ADMINISTRATOR")),
            Map.entry("GET /api/document-workflows/" + ID + "/change-requests",
                    List.of("DEVELOPER", "STAFF", "MANAGER", "TECHNICAL_LEAD", "ADMINISTRATOR")),
            Map.entry("POST /api/document-workflows/" + ID + "/comments", List.of("STAFF")),
            Map.entry("POST /api/document-workflows/" + ID + "/submit", List.of("DEVELOPER")),
            Map.entry("POST /api/document-workflows/" + ID + "/claim", List.of("STAFF")),
            Map.entry("POST /api/document-workflows/" + ID + "/release", List.of("STAFF")),
            Map.entry("POST /api/document-workflows/" + ID + "/staff-review", List.of("STAFF")),
            Map.entry("PUT /api/document-workflows/" + ID + "/document", List.of("DEVELOPER", "STAFF")),
            Map.entry("POST /api/document-workflows/" + ID + "/approve", List.of("MANAGER")),
            Map.entry("POST /api/document-workflows/" + ID + "/reject", List.of("MANAGER")),
            Map.entry("POST /api/document-workflows/" + ID + "/rollback",
                    List.of("DEVELOPER", "MANAGER", "TECHNICAL_LEAD")),
            Map.entry("POST /api/document-workflows/" + ID + "/reassign", List.of("ADMINISTRATOR")));

    static Stream<Arguments> routesAndRoles() {
        return ALLOWED.entrySet().stream().flatMap(entry -> ScreenPermissions.ROLES.stream()
                .map(role -> Arguments.of(entry.getKey(), role, entry.getValue().contains(role))));
    }

    @ParameterizedTest(name = "{1} on {0} -> allowed={2}")
    @MethodSource("routesAndRoles")
    void everyRouteFollowsTheMatrix(String route, String role, boolean allowed) {
        String[] parts = route.split(" ", 2);
        var decision = ApiRoutePermissions.evaluate(parts[0], parts[1], role);
        assertThat(decision.knownRoute()).as("route has a rule").isTrue();
        assertThat(decision.allowed()).isEqualTo(allowed);
    }

    @Test
    void legacyAdminIsTreatedAsAdministrator() {
        assertThat(ApiRoutePermissions.evaluate("GET", "/api/github/repos/available", "ADMIN").allowed()).isTrue();
        assertThat(ApiRoutePermissions.evaluate("GET", "/api/github/authorize-url", "ADMIN").allowed()).isFalse();
    }

    @Test
    void unknownOrMissingRolesAreRefusedEverywhere() {
        for (String role : new String[] {null, "", "GUEST", "ROLE_UNKNOWN"}) {
            assertThat(ApiRoutePermissions.evaluate("GET", "/api/github/connection", role).allowed())
                    .as("role " + role).isFalse();
        }
    }

    @Test
    void routesWithoutARuleAreRefused() {
        var decision = ApiRoutePermissions.evaluate("GET", "/api/documentation/templates/a/b/c", "TECHNICAL_LEAD");
        assertThat(decision.allowed()).isFalse();
        assertThat(decision.knownRoute()).isFalse();
        assertThat(ApiRoutePermissions.evaluate("PATCH", "/api/github/connection", "DEVELOPER").allowed()).isFalse();
        assertThat(ApiRoutePermissions.evaluate("DELETE", "/api/document-workflows/" + ID, "MANAGER").allowed()).isFalse();
    }

    @Test
    void everyRuleNamesRealScreensAndIsUsableByAtLeastOneRoleExceptTheRemovedDriftRoutes() {
        for (String description : ApiRoutePermissions.ruleDescriptions()) {
            String[] parts = description.split(" ", 2);
            String path = parts[1].replace("{}", "x");
            var needs = ApiRoutePermissions.needsFor(parts[0], path);
            boolean removedDrift = path.contains("/drift/") && !path.contains("severity-rules");
            if (removedDrift) {
                assertThat(needs).as(description).isEmpty();
                continue;
            }
            assertThat(needs).as(description).isNotEmpty();
            for (var need : needs) {
                assertThat(ScreenPermissions.screens()).as(description).contains(need.screen());
            }
            boolean someRole = ScreenPermissions.ROLES.stream()
                    .anyMatch(role -> ApiRoutePermissions.evaluate(parts[0], path, role).allowed());
            assertThat(someRole).as(description + " is allowed for at least one role").isTrue();
        }
    }
}
