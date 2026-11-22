package com.cnpm.backend.security;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

/**
 * Which row of the Screen Authorization matrix each GitHub Integration route needs.
 *
 * <p>Every browser request to {@code /api/github|workspaces|repositories|documentation|document-workflows/**}
 * goes through the BFF, which asks {@link #evaluate} before forwarding. The first matching rule wins; a rule lists
 * the screen/action pairs of which the role needs <em>at least one</em>. A route without a rule is refused
 * (deny by default), so a new route must be added here on purpose.
 *
 * <p>The matrix is an upper bound: GitHub Integration still applies its own checks (document ownership,
 * {@code DOCUMENT_*} authorities, workspace membership) on top.
 */
public final class ApiRoutePermissions {

    /** One acceptable (screen, action) pair. */
    public record Need(String screen, char action) {
    }

    private record Rule(String method, Pattern path, List<Need> anyOf, String description) {
    }

    /** The result of a check. */
    public record Decision(boolean allowed, boolean knownRoute, String reason) {
        static Decision allow() {
            return new Decision(true, true, "");
        }
    }

    private static final String ID = "[^/]+";
    private static final List<Rule> RULES = new ArrayList<>();

    private ApiRoutePermissions() {
    }

    private static Need need(String screen, char action) {
        return new Need(screen, action);
    }

    private static void rule(String method, String template, Need... anyOf) {
        String regex = "^" + template.replace("{}", ID) + "$";
        RULES.add(new Rule(method, Pattern.compile(regex), List.of(anyOf), method + " " + template));
    }

    static {
        // ---- GitHub connection (#5); the repository page also shows the connection status ----
        rule("GET", "/api/github/authorize-url", need("githubConnection", 'C'));
        rule("GET", "/api/github/callback", need("githubConnection", 'C'));
        rule("GET", "/api/github/connection", need("githubConnection", 'R'), need("repositories", 'R'));
        rule("DELETE", "/api/github/connection", need("githubConnection", 'D'));
        rule("GET", "/api/github/repos/available", need("repositories", 'R'));

        // ---- Repositories (#6); lists are also read by the documentation, search and activity screens ----
        rule("GET", "/api/workspaces/{}/repositories", need("repositories", 'R'), need("documentation", 'R'),
                need("pullRequests", 'R'), need("knowledgeBase", 'R'));
        rule("POST", "/api/workspaces/{}/repositories", need("repositories", 'C'));
        rule("PUT", "/api/workspaces/{}/repositories/{}", need("repositories", 'U'));
        rule("DELETE", "/api/workspaces/{}/repositories/{}", need("repositories", 'D'));
        rule("GET", "/api/repositories/{}", need("repositories", 'R'), need("pullRequests", 'R'),
                need("documentation", 'R'), need("knowledgeBase", 'R'));
        rule("DELETE", "/api/repositories/{}", need("repositories", 'D'));
        rule("POST", "/api/repositories/{}/sync", need("repositories", 'U'));
        rule("GET", "/api/repositories/{}/sync/latest", need("repositories", 'R'));
        rule("GET", "/api/repositories/{}/sync/latest/analysis-input", need("repositories", 'R'));
        rule("GET", "/api/repositories/{}/auto-update-policies", need("repositories", 'R'));
        rule("PUT", "/api/repositories/{}/auto-update-policies", need("repositories", 'U'));

        // ---- Pull requests, commits and source changes (#7) ----
        rule("GET", "/api/repositories/{}/pull-requests", need("pullRequests", 'R'));
        rule("GET", "/api/repositories/{}/commits", need("pullRequests", 'R'));
        rule("GET", "/api/repositories/{}/source-changes", need("pullRequests", 'R'));
        rule("POST", "/api/repositories/{}/source-changes/{}/retry", need("repositories", 'U'));

        // ---- Documentation generation, editing and reading (#8, #20) ----
        rule("POST", "/api/repositories/{}/documentation/generate", need("documentation", 'C'));
        rule("GET", "/api/repositories/{}/documentation/search", need("knowledgeBase", 'R'));
        rule("GET", "/api/repositories/{}/documentation", need("documentation", 'R'), need("knowledgeBase", 'R'));
        rule("GET", "/api/repositories/{}/code-entities", need("documentation", 'R'), need("knowledgeBase", 'R'));
        rule("GET", "/api/documentation/jobs/{}", need("documentation", 'R'));
        rule("GET", "/api/documentation/jobs/{}/result", need("documentation", 'R'));
        rule("GET", "/api/documentation/jobs/{}/report", need("documentation", 'R'));
        rule("POST", "/api/documentation/jobs/{}/document", need("documentation", 'C'), need("workflowSubmission", 'C'));
        rule("GET", "/api/documentation/code-entities/{}/documents", need("documentation", 'R'), need("knowledgeBase", 'R'));

        // ---- Documentation collections and assigned ownership (#21) ----
        String collections = "/api/workspaces/{}/collections";
        rule("GET", collections, need("collections", 'R'));
        rule("GET", collections + "/{}/documents", need("collections", 'R'));
        rule("GET", collections + "/{}/document-candidates", need("collections", 'U'));
        rule("POST", collections, need("collections", 'C'));
        rule("PUT", collections + "/{}", need("collections", 'U'));
        rule("DELETE", collections + "/{}", need("collections", 'D'));
        rule("PUT", collections + "/{}/documents/{}", need("collections", 'U'));
        rule("DELETE", collections + "/{}/documents/{}", need("collections", 'U'));
        rule("PUT", collections + "/{}/documents/{}/owner/{}", need("collections", 'U'));
        rule("DELETE", collections + "/{}/documents/{}/owner", need("collections", 'U'));

        // ---- Documentation templates (#22); the generation screen only reads them ----
        rule("GET", "/api/documentation/templates", need("templates", 'R'), need("documentation", 'R'));
        rule("GET", "/api/documentation/templates/sections", need("templates", 'R'), need("documentation", 'R'));
        rule("GET", "/api/documentation/templates/{}", need("templates", 'R'), need("documentation", 'R'));
        rule("GET", "/api/documentation/templates/{}/versions", need("templates", 'R'));
        rule("GET", "/api/documentation/templates/{}/versions/{}", need("templates", 'R'));
        rule("POST", "/api/documentation/templates/{}/versions/{}/restore", need("templates", 'U'));
        rule("POST", "/api/documentation/templates", need("templates", 'C'));
        rule("PUT", "/api/documentation/templates/{}", need("templates", 'U'));
        rule("DELETE", "/api/documentation/templates/{}", need("templates", 'D'));

        // ---- Drift (#16 was removed for every role; thresholds #17 stay for Technical Lead) ----
        rule("GET", "/api/documentation/drift/severity-rules", need("driftPolicies", 'R'));
        rule("POST", "/api/repositories/{}/drift/analyze", need("driftAlerts", 'C'));
        rule("GET", "/api/repositories/{}/drift/reports", need("driftAlerts", 'R'));
        rule("GET", "/api/repositories/{}/drift/reports/{}", need("driftAlerts", 'R'));
        rule("GET", "/api/repositories/{}/drift/reports/{}/markdown", need("driftAlerts", 'R'));
        rule("PUT", "/api/repositories/{}/drift/reports/{}/findings/{}/resolution", need("driftAlerts", 'U'));

        // ---- One saved document and its code links (#8, #20) ----
        rule("GET", "/api/documentation/{}", need("documentation", 'R'), need("knowledgeBase", 'R'));
        rule("GET", "/api/documentation/{}/code-entities", need("documentation", 'R'), need("knowledgeBase", 'R'));
        rule("PUT", "/api/documentation/{}/code-entities", need("documentation", 'U'));

        // ---- Review and approval workflow (#9, #10, #11, #13, #19) ----
        rule("POST", "/api/document-workflows", need("workflowSubmission", 'C'));
        rule("GET", "/api/document-workflows/mine", need("workflowSubmission", 'R'));
        rule("GET", "/api/document-workflows/staff/queue", need("staffReview", 'R'));
        rule("GET", "/api/document-workflows/manager/queue", need("managerApproval", 'R'));
        rule("GET", "/api/document-workflows/history-accessible", need("workflowSubmission", 'R'),
                need("staffReview", 'R'), need("managerApproval", 'R'), need("approvalAudit", 'R'));
        // "/versions" and "/comparison" (LD-183): compare two versions of the workflow's document. They are read
        // views like "/history"; GitHub Integration still checks that the user may read this workflow.
        for (String view : new String[] {"", "/document", "/evidence", "/review-evidence", "/review-comparison",
                "/history", "/comments", "/change-requests", "/versions", "/comparison"}) {
            rule("GET", "/api/document-workflows/{}" + view, need("workflowSubmission", 'R'),
                    need("staffReview", 'R'), need("managerApproval", 'R'), need("approvalAudit", 'R'));
        }
        rule("POST", "/api/document-workflows/{}/submit", need("workflowSubmission", 'C'));
        rule("POST", "/api/document-workflows/{}/claim", need("staffReview", 'U'));
        rule("POST", "/api/document-workflows/{}/release", need("staffReview", 'U'));
        rule("POST", "/api/document-workflows/{}/staff-review", need("staffReview", 'A'));
        rule("POST", "/api/document-workflows/{}/comments", need("staffReview", 'A'));
        rule("PUT", "/api/document-workflows/{}/document", need("documentation", 'U'));
        rule("POST", "/api/document-workflows/{}/approve", need("managerApproval", 'A'));
        rule("POST", "/api/document-workflows/{}/versions/{}/github-commit", need("managerApproval", 'A'));
        rule("POST", "/api/document-workflows/{}/reject", need("managerApproval", 'A'));
        rule("POST", "/api/document-workflows/{}/rollback", need("documentRollback", 'U'));
        // Reassigning a review to another Staff member is an administration task (also needs DOCUMENT_REASSIGN).
        rule("POST", "/api/document-workflows/{}/reassign", need("userManagement", 'U'));
    }

    /**
     * Checks a request.
     *
     * @param method HTTP method
     * @param path   request path without the query string
     * @param role   the account's primary role (any spelling accepted by {@link ScreenPermissions#normalizeRole})
     */
    public static Decision evaluate(String method, String path, String role) {
        String upperMethod = method == null ? "" : method.toUpperCase(Locale.ROOT);
        for (Rule rule : RULES) {
            if (!rule.method().equals(upperMethod) || !rule.path().matcher(path).matches()) continue;
            boolean allowed = rule.anyOf().stream()
                    .anyMatch(need -> ScreenPermissions.can(role, need.screen(), need.action()));
            return allowed
                    ? Decision.allow()
                    : new Decision(false, true, "Your role is not permitted to perform this action.");
        }
        return new Decision(false, false, "This route is not available.");
    }

    /** The (screen, action) pairs a route accepts; empty for an unknown route or one refused for every role. */
    public static List<Need> needsFor(String method, String path) {
        String upperMethod = method == null ? "" : method.toUpperCase(Locale.ROOT);
        return RULES.stream()
                .filter(rule -> rule.method().equals(upperMethod) && rule.path().matcher(path).matches())
                .findFirst().map(Rule::anyOf).orElse(List.of());
    }

    /** Every rule as "METHOD /path": lets tests list the routes that are covered. */
    public static List<String> ruleDescriptions() {
        return RULES.stream().map(Rule::description).toList();
    }
}
