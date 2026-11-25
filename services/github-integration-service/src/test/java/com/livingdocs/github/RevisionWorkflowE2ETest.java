package com.livingdocs.github;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Set;
import org.springframework.data.domain.PageRequest;
import org.springframework.web.client.RestClient;
import com.livingdocs.github.service.DocumentWorkflowService;
import com.livingdocs.github.repository.DocumentWorkflowRepository;
import com.livingdocs.github.entity.StaffReviewResult;
import com.livingdocs.github.entity.ManagerDecision;
import com.livingdocs.github.dto.WorkflowDtos.StaffReviewRequest;
import com.livingdocs.github.dto.WorkflowDtos.EditDocumentRequest;
import com.livingdocs.github.client.GitHubCommit;
import com.fasterxml.jackson.databind.JsonNode;
import com.livingdocs.github.change.CodeAnalyzerClient;
import com.livingdocs.github.change.CodeEntity;
import com.livingdocs.github.client.GitHubBlob;
import com.livingdocs.github.client.GitHubChangedFile;
import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.client.GitHubRepo;
import com.livingdocs.github.client.GitHubTree;
import com.livingdocs.github.client.GitHubPullRequest;
import com.livingdocs.github.entity.ConnectionStatus;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.repository.GitHubConnectionRepository;
import com.livingdocs.github.service.DocumentCommitBackService;
import com.livingdocs.github.sync.AnalysisInput;
import org.mockito.invocation.InvocationOnMock;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** Runs against a real FastAPI listener and an isolated PostgreSQL database. */
@SpringBootTest(properties = {
        "spring.datasource.url=${LIVINGDOCS_E2E_DB_URL:jdbc:postgresql://postgres:5432/revision_e2e}",
        "spring.datasource.username=revision_test",
        "spring.datasource.password=fixture-password",
        "spring.datasource.driver-class-name=org.postgresql.Driver",
        "spring.jpa.hibernate.ddl-auto=validate",
        "services.ai-service.base-url=${LIVINGDOCS_E2E_AI_URL}"
})
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(com.livingdocs.github.security.InternalServiceTestMvcConfig.class)
@org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable(named = "LIVINGDOCS_E2E_AI_URL", matches = ".+")
class RevisionWorkflowE2ETest {
    private static final String USER_HEADER = "X-User-Id";
    private static final String WEBHOOK_SECRET = "test-only-webhook-secret"; // application-test.yml
    private static final String TOKEN = "ghu_source_change_token";
    private static final String BLOB = "b1".repeat(20);
    private static final String PATH = "src/main/java/acme/Invoice.java";
    /** Mỗi test một repo GitHub riêng, để webhook của test này không chạm tới repo của test khác. */
    private static final AtomicLong NEXT_GITHUB_REPO_ID = new AtomicLong(6_161_000L);

    // Invoice.java: total() đổi giá trị trả về, discount() bị thay bằng tax()
    private static final String BEFORE = String.join("\n",
            "public class Invoice {", "    int total() {", "        return 1;", "    }", "",
            "    int discount() {", "        return 0;", "    }", "}") + "\n";
    private static final String AFTER = String.join("\n",
            "public class Invoice {", "    int total() {", "        return 2;", "    }", "",
            "    int tax() {", "        return 1;", "    }", "}") + "\n";
    private static final String PATCH = String.join("\n",
            "@@ -1,9 +1,9 @@", " public class Invoice {", "     int total() {", "-        return 1;", "+        return 2;",
            "     }", " ", "-    int discount() {", "-        return 0;", "+    int tax() {", "+        return 1;", "     }", " }");


    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;

    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.ValueSource(booleans = {false, true})
    @org.junit.jupiter.api.condition.DisabledIfEnvironmentVariable(named = "LIVINGDOCS_E2E_RESTART_PHASE", matches = ".+")
    void recoversPersistedOwnerEditOnRetryOrSubmit(boolean resubmit) throws Exception {
        String owner = Long.toString(java.util.concurrent.ThreadLocalRandom.current().nextLong(1000, Long.MAX_VALUE));
        var ai = aiService.mutate().defaultHeader(USER_HEADER, owner).build();
        var job = ai.post().uri("/generate").contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("scope", "file", "target", PATH, "output_language", "en", "files",
                        List.of(Map.of("path", PATH, "language", "java", "classes",
                                List.of(Map.of("name", "Invoice", "lineno", 1))))))
                .retrieve().body(JsonNode.class);
        String jobId = job.path("id").asText();
        await(() -> ai.get().uri("/jobs/{id}", jobId).retrieve().body(JsonNode.class)
                .path("status").asText().equals("completed"));
        var document = ai.post().uri("/internal/documents/from-job").contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("job_id", jobId, "actor_role", "DEVELOPER")).retrieve().body(JsonNode.class);
        String docId = document.path("id").asText();
        var permissions = Set.of("DOCUMENT_CREATE", "DOCUMENT_SUBMIT", "DOCUMENT_UPDATE", "DOCUMENT_VIEW", "ROLE_STAFF");
        var staff = Set.of("DOCUMENT_CLAIM", "DOCUMENT_REVIEW", "ROLE_STAFF");
        UUID id = workflows.create(owner, permissions, docId).id();
        assertThat(workflows.history(owner, permissions, id)).filteredOn(event -> event.action().equals("DOCUMENT_GENERATED"))
                .singleElement().satisfies(event -> {
                    assertThat(event.actorUserId()).isEqualTo(owner);
                    assertThat(event.actorRole()).isEqualTo("DEVELOPER");
                    assertThat(event.triggerSource()).isEqualTo("INITIAL_GENERATION");
                    assertThat(event.documentVersion()).isEqualTo(1);
                    assertThat(event.createdAt()).isEqualTo(Instant.parse(
                            document.path("initial_generation_save").path("saved_at").asText()));
                });
        workflows.submit(owner, permissions, id, 1);
        workflows.claim("audit-staff", staff, id);
        workflows.staffReview("audit-staff", staff, id,
                new StaffReviewRequest(StaffReviewResult.CHANGES_REQUESTED, "Clarify the description"));

        // Save through the real AI API and omit the Java audit, as if the response had been lost.
        var persisted = ai.put().uri("/internal/documents/{id}/content", docId)
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("expected_version", 1, "content", "Revised", "note", "Clarified",
                        "actor_role", "DEVELOPER")).retrieve().body(JsonNode.class);
        var request = new EditDocumentRequest("Revised", "Clarified", 1);
        assertThatThrownBy(() -> workflows.editAfterChanges("unrelated", permissions, id, request))
                .isInstanceOf(com.livingdocs.github.exception.ApiException.class);
        if (!resubmit) {
            workflows.editAfterChanges(owner, permissions, id, request);
            workflows.editAfterChanges(owner, permissions, id, request);
        }
        workflows.submit(owner, permissions, id, 2);
        assertThat(workflows.history(owner, permissions, id)).filteredOn(event -> event.action().equals("DOCUMENT_EDITED"))
                .singleElement().satisfies(event -> {
                    assertThat(event.actorRole()).isEqualTo("DEVELOPER");
                    assertThat(event.triggerSource()).isEqualTo("MANUAL_EDIT");
                    assertThat(event.documentVersion()).isEqualTo(2);
                    assertThat(event.createdAt()).isEqualTo(Instant.parse(persisted.path("created_at").asText()));
                });
        assertThat(ai.get().uri("/internal/documents/{id}", docId).retrieve().body(JsonNode.class)
                .path("versions_total").asInt()).isEqualTo(2);
    }
    @Autowired GitHubConnectionRepository connectionRepository;
    @Autowired DocumentWorkflowService workflows;
    @Autowired DocumentCommitBackService commitBack;
    @Autowired DocumentWorkflowRepository workflowRows;
    @Autowired org.springframework.transaction.support.TransactionTemplate transactions;
    @Autowired org.springframework.jdbc.core.JdbcTemplate revisionJdbc;
    @Autowired com.livingdocs.github.change.RevisionJobWorker revisionWorker;
    @Autowired @org.springframework.beans.factory.annotation.Qualifier("aiServiceRestClient")
    RestClient aiService;

    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.ValueSource(strings = {"11", "15", "16"})
    @org.junit.jupiter.api.condition.DisabledIfEnvironmentVariable(named = "LIVINGDOCS_E2E_RESTART_PHASE", matches = ".+")
    void upgradesExistingPostgresSchemaToV20(String version) {
        String schema = "upgrade_v" + version;
        var dataSource = new org.postgresql.ds.PGSimpleDataSource();
        dataSource.setURL(System.getenv().getOrDefault("LIVINGDOCS_E2E_DB_URL",
                "jdbc:postgresql://postgres:5432/revision_e2e"));
        dataSource.setUser("revision_test");
        dataSource.setPassword("fixture-password");
        dataSource.setCurrentSchema(schema);
        var selector = new com.livingdocs.github.config.FlywayMigrationLineageSelector();
        String initial = version.equals("11") ? com.livingdocs.github.config.FlywayMigrationLineageSelector.LEGACY_LOCATION
                : com.livingdocs.github.config.FlywayMigrationLineageSelector.CURRENT_LOCATION;
        org.flywaydb.core.Flyway.configure().dataSource(dataSource).schemas(schema)
                .locations(initial, "classpath:db/migration-common").target(version).load().migrate();

        String selected = selector.select(dataSource).location();
        var flyway = org.flywaydb.core.Flyway.configure().dataSource(dataSource).schemas(schema)
                .locations(selected, "classpath:db/migration-common").load();
        flyway.migrate();
        flyway.validate();
        assertThat(flyway.info().current().getVersion().toString()).isEqualTo("20");
        var jdbc = new org.springframework.jdbc.core.JdbcTemplate(dataSource);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM legacy_drift_owner_attestations", Long.class))
                .isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(trigger_source) FROM document_workflow_audit", Long.class))
                .isZero();
    }

    @org.junit.jupiter.api.Test
    @org.junit.jupiter.api.condition.DisabledIfEnvironmentVariable(named = "LIVINGDOCS_E2E_RESTART_PHASE", matches = ".+")
    void driftAccessTracksCurrentRepositoryAssociation() throws Exception {
        String owner = Long.toString(java.util.concurrent.ThreadLocalRandom.current().nextLong(1, Long.MAX_VALUE));
        var original = connectAndAddRepo(owner);
        var other = addRepo(owner);
        String firstWorkspace = "workspace-" + UUID.randomUUID();
        String otherWorkspace = "workspace-" + UUID.randomUUID();
        String newWorkspace = "workspace-" + UUID.randomUUID();
        UUID originalId = UUID.fromString(original.id());
        revisionJdbc.update("UPDATE repositories SET workspace_id = ? WHERE id = ?", firstWorkspace, originalId);
        revisionJdbc.update("UPDATE repositories SET workspace_id = ? WHERE id = ?",
                otherWorkspace, UUID.fromString(other.id()));
        var report = aiService.post().uri("/drift/analyze").contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("repository", "acme/docs", "pull_request", Map.of("number", 7),
                        "files", List.of(Map.of("path", "README.md")), "document_ids", List.of()))
                .retrieve().body(JsonNode.class);
        String id = report.path("id").asText();
        revisionJdbc.update("INSERT INTO legacy_drift_owner_attestations VALUES (?, ?, ?, ?)",
                id, originalId, owner, "fixture audit with exact report and repository IDs");
        String list = "/api/repositories/{repo}/drift/reports";
        String detail = list + "/{report}";
        String markdown = detail + "/markdown";
        mvc.perform(get(detail, original.id(), id).header(USER_HEADER, owner)
                .header("X-Verified-Workspace-Id", firstWorkspace).header("X-Verified-Workspace-Access", "OWNER"))
                .andExpect(status().isOk());
        mvc.perform(get(detail, other.id(), id).header(USER_HEADER, owner)
                .header("X-Verified-Workspace-Id", otherWorkspace).header("X-Verified-Workspace-Access", "OWNER"))
                .andExpect(status().isNotFound());

        revisionJdbc.update("UPDATE repositories SET workspace_id = ? WHERE id = ?", newWorkspace, originalId);
        mvc.perform(get(detail, original.id(), id).header(USER_HEADER, owner)
                .header("X-Verified-Workspace-Id", firstWorkspace).header("X-Verified-Workspace-Access", "OWNER"))
                .andExpect(status().isForbidden());
        mvc.perform(get(detail, original.id(), id).header(USER_HEADER, owner)
                .header("X-Verified-Workspace-Id", newWorkspace).header("X-Verified-Workspace-Access", "OWNER"))
                .andExpect(status().isOk());
        var connection = connectionRepository.findByUserId(owner).orElseThrow();
        connection.setStatus(ConnectionStatus.INVALID);
        connectionRepository.save(connection);

        mvc.perform(get("/api/drift/reports/{report}", id).header(USER_HEADER, owner))
                .andExpect(status().isForbidden());
        mvc.perform(get(list, original.id()).header(USER_HEADER, owner)
                .header("X-Verified-Workspace-Id", newWorkspace).header("X-Verified-Workspace-Access", "OWNER"))
                .andExpect(status().isForbidden());
        for (String route : List.of(detail, markdown)) {
            mvc.perform(get(route, original.id(), id).header(USER_HEADER, owner)
                    .header("X-Verified-Workspace-Id", newWorkspace).header("X-Verified-Workspace-Access", "OWNER"))
                    .andExpect(status().isForbidden());
        }
        mvc.perform(put(detail + "/findings/F1/resolution", original.id(), id).header(USER_HEADER, owner)
                .header("X-Verified-Workspace-Id", newWorkspace).header("X-Verified-Workspace-Access", "OWNER")
                .contentType(MediaType.APPLICATION_JSON).content("{\"status\":\"resolved\"}"))
                .andExpect(status().isForbidden());
    }

    @MockitoBean GitHubClient gitHubClient;
    @MockitoBean CodeAnalyzerClient analyzerClient;
    @MockitoBean(name = "codeAnalyzerRestClient", answers = org.mockito.Answers.RETURNS_DEEP_STUBS)
    RestClient revisionAnalyzer;

    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.CsvSource({
            "accept, false", "edit, false", "dismiss, false", "accept, true", "edit, true"
    })
    @org.junit.jupiter.api.condition.DisabledIfEnvironmentVariable(named = "LIVINGDOCS_E2E_RESTART_PHASE", matches = ".+")
    void driftDecisionUsesRealAiHttpAndExactReviewVersion(String decision, boolean sqlCommittedFirst) throws Exception {
        String owner = Long.toString(java.util.concurrent.ThreadLocalRandom.current().nextLong(1, Long.MAX_VALUE));
        var repo = connectAndAddRepo(owner);
        var ai = aiService.mutate().defaultHeader(USER_HEADER, owner).build();
        String templateName = "Drift template " + UUID.randomUUID();
        var template = ai.post().uri("/templates").contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("name", templateName, "instructions", "Describe the source.",
                        "sections", List.of("Overview", "Classes")))
                .retrieve().body(JsonNode.class);
        String templateId = template.path("id").asText();
        String base = newSha(), head = newSha();
        var previousFile = Map.of("path", PATH, "language", "java",
                "classes", List.of(Map.of("name", "Invoice", "lineno", 1)));
        var job = ai.post().uri("/generate").contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("scope", "file", "target", PATH, "output_language", "en", "template_id", templateId,
                        "files", List.of(previousFile), "source_snapshot",
                        Map.of("repository_id", repo.id(), "repository_full_name", "acme/docs",
                                "branch", "main", "commit_sha", base)))
                .retrieve().body(JsonNode.class);
        String jobId = job.path("id").asText();
        await(() -> ai.get().uri("/jobs/{id}", jobId).retrieve().body(JsonNode.class)
                .path("status").asText().equals("completed"));
        var document = ai.post().uri("/internal/documents/from-job").contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("job_id", jobId)).retrieve().body(JsonNode.class);
        String documentId = document.path("id").asText();
        var staff = Set.of("ROLE_STAFF", "DOCUMENT_CLAIM", "DOCUMENT_REVIEW");
        var manager = Set.of("ROLE_MANAGER", "DOCUMENT_APPROVE");
        var developer = Set.of("DOCUMENT_CREATE", "DOCUMENT_SUBMIT");
        UUID workflow = workflows.create(owner, developer, documentId).id();
        workflows.submit(owner, developer, workflow, 1);
        workflows.claim("staff", staff, workflow);
        workflows.staffReview("staff", staff, workflow, new StaffReviewRequest(StaffReviewResult.PASSED, null));
        workflows.decide("manager", manager, workflow, ManagerDecision.APPROVED, null, 1);
        String baselineContent = ai.get().uri("/internal/documents/{id}/content", documentId)
                .retrieve().body(String.class);
        ai.put().uri("/templates/{id}", templateId).contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("name", templateName, "instructions", "Describe the new format.",
                        "sections", List.of("Overview", "API Endpoints")))
                .retrieve().toBodilessEntity();

        var report = ai.post().uri("/drift/analyze").contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("repository", "acme/docs", "document_ids", List.of(documentId),
                        "pull_request", Map.of("number", 7, "head_branch", "feature", "base_branch", "main",
                                "head_sha", head, "base_sha", base, "base_head_sha", base),
                        "files", List.of(Map.of("path", PATH, "status", "modified", "before", previousFile,
                                "after", Map.of("path", PATH, "language", "java",
                                        "classes", List.of(Map.of("name", "Receipt", "lineno", 1)))))))
                .retrieve().body(JsonNode.class);
        String reportId = report.path("id").asText();
        String findingId = report.path("findings").get(0).path("id").asText();
        revisionJdbc.update("INSERT INTO drift_report_owners (report_id, repository_id, owner_user_id) VALUES (?, ?, ?)",
                reportId, UUID.fromString(repo.id()), owner);
        String endpoint = "/api/repositories/{repo}/drift/reports/{report}/findings/{finding}/resolution";
        boolean dismiss = decision.equals("dismiss");
        var body = json.writeValueAsBytes(Map.of("status", dismiss ? "dismissed" : "acknowledged",
                "decision", decision, "note", "Reviewed drift",
                "proposed", baselineContent.replace("`Invoice`", "`Receipt`")));
        var request = put(endpoint, repo.id(), reportId, findingId).header(USER_HEADER, owner)
                .contentType(MediaType.APPLICATION_JSON).content(body);
        if (!dismiss) {
            var stale = new GitHubPullRequest.Ref("feature", newSha());
            when(gitHubClient.getPullRequest(TOKEN, "acme", "docs", 7)).thenReturn(new GitHubPullRequest(
                    7, "Rename Invoice", null, "open", null, null, stale, new GitHubPullRequest.Ref("main", base),
                    null, null, null, null));
            mvc.perform(request).andExpect(status().isConflict());
        }
        when(gitHubClient.getPullRequest(TOKEN, "acme", "docs", 7)).thenReturn(new GitHubPullRequest(
                7, "Rename Invoice", null, "open", null, null, new GitHubPullRequest.Ref("feature", head),
                new GitHubPullRequest.Ref("main", base), null, null, null, null));
        if (decision.equals("edit")) {
            var invalid = Map.of("status", "acknowledged", "decision", "edit", "proposed",
                    "# " + PATH + "\n\n## Overview\n\nMissing Classes.");
            mvc.perform(put(endpoint, repo.id(), reportId, findingId).header(USER_HEADER, owner)
                    .contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsBytes(invalid)))
                    .andExpect(status().isConflict());
            assertThat(workflowRows.findById(workflow).orElseThrow().getSubmittedDocumentVersion()).isEqualTo(1);
        }
        var result = mvc.perform(request).andExpect(status().isOk());
        mvc.perform(request).andExpect(status().isOk()).andExpect(jsonPath("$.resolution.history.length()").value(1));
        if (dismiss) {
            result.andExpect(jsonPath("$.resolution.draft_version").doesNotExist());
            assertThat(workflowRows.findById(workflow).orElseThrow().getSubmittedDocumentVersion()).isEqualTo(1);
            return;
        }
        result.andExpect(jsonPath("$.resolution.draft_version").value(2));
        var draft = ai.get().uri("/internal/documents/{id}/versions/2", documentId).retrieve().body(JsonNode.class);
        assertThat(draft.path("source_snapshot").path("commit_sha").asText()).isEqualTo(head);
        assertThat(draft.path("drift_finding").path("evidence").isEmpty()).isFalse();
        workflows.claim("staff", staff, workflow);
        var reviewedDraft = workflows.reviewComparison("staff", staff, workflow).path("pending_version");
        assertThat(reviewedDraft.path("evidence_report").path("template_version").asInt()).isEqualTo(1);
        assertThat(reviewedDraft.path("evidence_report").path("template_sections"))
                .extracting(JsonNode::asText).containsExactly("Overview", "Classes");
        assertThat(reviewedDraft.path("content").asText()).startsWith("# " + PATH + "\n")
                .contains("## Overview", "## Classes", draft.path("drift_finding").path("proposed").asText());
        if (decision.equals("edit")) {
            assertThat(reviewedDraft.path("content").asText()).contains("`Receipt`");
        }
        workflows.staffReview("staff", staff, workflow, new StaffReviewRequest(StaffReviewResult.PASSED, null));
        assertThatThrownBy(() -> workflows.decide("manager", manager, workflow, ManagerDecision.APPROVED, null, 1))
                .isInstanceOf(com.livingdocs.github.exception.ApiException.class);
        boolean approved = decision.equals("accept");
        ManagerDecision outcome = approved ? ManagerDecision.APPROVED : ManagerDecision.REJECTED;
        String note = approved ? "Approved after review" : "Needs correction";
        var permissions = Set.of("ROLE_MANAGER", "DOCUMENT_APPROVE", "DOCUMENT_REJECT");
        if (sqlCommittedFirst) {
            // Simulate losing the AI write after the workflow and its audit committed together.
            transactions.executeWithoutResult(transaction -> {
                var saved = workflowRows.findById(workflow).orElseThrow();
                saved.decide("manager", outcome, note);
                workflowRows.saveAndFlush(saved);
                revisionJdbc.update("""
                        INSERT INTO document_workflow_audit
                          (id, workflow_id, actor_user_id, actor_role, action, previous_status,
                           new_status, comment, document_version, created_at)
                        VALUES (?, ?, 'manager', 'MANAGER', ?, 'PENDING_MANAGER_APPROVAL', ?, ?, 2, CURRENT_TIMESTAMP)
                        """, UUID.randomUUID(), workflow, outcome.name(), outcome.name(), note);
            });
        } else {
            // Persist the remote decision while SQL is still pending, as after a Java crash.
            aiService.post().uri("/internal/documents/{id}/review-decision", documentId)
                    .header(USER_HEADER, "manager").header("X-Document-Owner-Id", owner)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("version", 2, "decision", outcome.name(), "note", note))
                    .retrieve().toBodilessEntity();
            assertThatThrownBy(() -> workflows.decide("manager-b", permissions, workflow, outcome, note, 2))
                    .isInstanceOf(com.livingdocs.github.exception.ApiException.class);
            assertThatThrownBy(() -> workflows.decide("manager", permissions, workflow, outcome, "Changed note", 2))
                    .isInstanceOf(com.livingdocs.github.exception.ApiException.class);
            assertThat(workflowRows.findById(workflow).orElseThrow().getStatus().name())
                    .isEqualTo("PENDING_MANAGER_APPROVAL");
            workflows.decide("manager", permissions, workflow, outcome, note, 2);
        }
        String listRoute = "/api/repositories/{repo}/drift/reports";
        String detailRoute = listRoute + "/{report}";
        if (approved) {
            mvc.perform(get(detailRoute, repo.id(), reportId).header(USER_HEADER, owner)
                    .param("minSeverity", "critical")).andExpect(status().isOk())
                    .andExpect(jsonPath("$.review.resolved").value(1));
        } else {
            mvc.perform(get(detailRoute + "/markdown", repo.id(), reportId).header(USER_HEADER, owner))
                    .andExpect(status().isOk())
                    .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.content()
                            .string(org.hamcrest.Matchers.containsString("open by manager")));
        }
        mvc.perform(get(listRoute, repo.id()).header(USER_HEADER, owner)).andExpect(status().isOk())
                .andExpect(jsonPath("$[0].review.acknowledged").value(0));
        mvc.perform(get(detailRoute, repo.id(), reportId).header(USER_HEADER, owner)).andExpect(status().isOk())
                .andExpect(jsonPath("$.findings[0].resolution.actor").value("manager"))
                .andExpect(jsonPath("$.findings[0].resolution.note").value(note));
        assertThat(ai.get().uri("/internal/documents/{id}", documentId).retrieve().body(JsonNode.class)
                .path("current_version").asInt()).isEqualTo(approved ? 2 : 1);
        workflows.decide("manager", permissions, workflow, outcome, note, 2);
        assertThat(revisionJdbc.queryForList("""
                SELECT actor_user_id, comment FROM document_workflow_audit
                WHERE workflow_id = ? AND document_version = 2 AND action = ?
                """, workflow, outcome.name())).containsExactly(Map.of("actor_user_id", "manager", "comment", note));
    }

    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.EnumSource(value = Scenario.class,
            mode = org.junit.jupiter.params.provider.EnumSource.Mode.EXCLUDE, names = "STAGE_RESTART")
    @org.junit.jupiter.api.condition.DisabledIfEnvironmentVariable(named = "LIVINGDOCS_E2E_RESTART_PHASE", matches = ".+")
    void signedWebhookRequiresStaffAndExactManagerDecision(Scenario scenario) throws Exception {
        String owner = Long.toString(java.util.concurrent.ThreadLocalRandom.current().nextLong(1, Long.MAX_VALUE));
        var repo = connectAndAddRepo(owner);
        String sha = newSha();
        var commit = new GitHubCommit(sha, null, null, null);
        when(gitHubClient.getCommit(TOKEN, "acme", "docs", "main")).thenReturn(commit);
        when(gitHubClient.getCommitFiles(TOKEN, "acme", "docs", sha)).thenReturn(List.of(invoiceFile(PATCH)));
        mockInvoiceContentAndAnalyzer();
        var analysisResponse = json.createObjectNode();
        analysisResponse.putArray("files").addObject().put("path", PATH).put("language", "java")
                .putArray("classes").addObject().put("name", "Invoice").put("lineno", 1)
                .put("docstring", "Includes tax in the total.");
        var analysisCalls = new AtomicInteger();
        var firstWorker = new CountDownLatch(1);
        var releaseFirstWorker = new CountDownLatch(1);
        when(revisionAnalyzer.post().uri("/api/v1/analyze-repo")
                .body(org.mockito.ArgumentMatchers.any(AnalysisInput.class)).retrieve()
                .body(JsonNode.class)).thenAnswer(invocation -> {
                    if (analysisCalls.incrementAndGet() == 1) {
                        if (scenario == Scenario.RETRY || scenario == Scenario.STAGE_RESTART) {
                            return json.createObjectNode();
                        }
                        if (scenario == Scenario.REPLACE_WORKER) {
                            firstWorker.countDown();
                            assertThat(releaseFirstWorker.await(20, TimeUnit.SECONDS)).isTrue();
                        }
                    }
                    return analysisResponse;
                });

        var ai = aiService.mutate().defaultHeader(USER_HEADER, owner).build();
        var analysis = Map.of("path", PATH, "language", "java", "classes",
                List.of(Map.of("name", "Invoice", "lineno", 1)));
        String templateName = "Invoice revision " + UUID.randomUUID();
        var template = ai.post().uri("/templates").contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("name", templateName, "instructions", "Describe the source.",
                        "sections", List.of("Overview", "Classes")))
                .retrieve().body(JsonNode.class);
        String templateId = template.path("id").asText();
        assertThat(template.path("version").asInt()).isEqualTo(1);
        var job = ai.post().uri("/generate").contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("scope", "file", "target", PATH,
                "output_language", "en", "files", List.of(analysis), "template_id", templateId,
                "template_version", 1, "source_snapshot",
                Map.of("repository_id", repo.id(), "repository_full_name", "acme/docs",
                        "branch", "main", "commit_sha", newSha()))).retrieve().body(JsonNode.class);
        String jobId = job.path("id").asText();
        await(() -> ai.get().uri("/jobs/{id}", jobId).retrieve().body(JsonNode.class)
                .path("status").asText().equals("completed"));
        var document = ai.post().uri("/internal/documents/from-job").contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("job_id", jobId))
                .retrieve().body(JsonNode.class);
        String documentId = document.path("id").asText();
        assertThat(document.path("pending_version").asInt()).isEqualTo(1);
        String manager = "revision-manager";
        String staff = "revision-staff";
        var staffPermissions = Set.of("ROLE_STAFF", "DOCUMENT_CLAIM", "DOCUMENT_REVIEW");
        var managerPermissions = Set.of("ROLE_MANAGER", "DOCUMENT_APPROVE", "DOCUMENT_REJECT");
        var ownerPermissions = Set.of("DOCUMENT_CREATE", "DOCUMENT_SUBMIT");
        UUID id = workflows.create(owner, ownerPermissions, documentId).id();
        workflows.submit(owner, ownerPermissions, id, 1);
        workflows.claim(staff, staffPermissions, id);
        workflows.staffReview(staff, staffPermissions, id,
                new StaffReviewRequest(StaffReviewResult.PASSED, "Baseline for source revision"));
        workflows.decide(manager, managerPermissions, id, ManagerDecision.APPROVED, null, 1);
        var updatedTemplate = ai.put().uri("/templates/{id}", templateId).contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("name", templateName, "instructions", "Describe the new format.",
                        "sections", List.of("Overview", "API Endpoints")))
                .retrieve().body(JsonNode.class);
        assertThat(updatedTemplate.path("version").asInt()).isEqualTo(2);
        if (scenario == Scenario.POLICY_DISABLED || scenario == Scenario.DOCUMENT_OVERRIDE) {
            var rules = new java.util.ArrayList<Map<String, Object>>();
            rules.add(Map.of("scope", "REPOSITORY", "target", "", "onCommit", true, "onPullRequest", false));
            rules.add(Map.of("scope", "MODULE", "target", "src/main", "onCommit", false, "onPullRequest", true));
            if (scenario == Scenario.DOCUMENT_OVERRIDE) {
                rules.add(Map.of("scope", "DOCUMENT", "target", documentId, "onCommit", true, "onPullRequest", false));
            }
            mvc.perform(put("/api/repositories/{id}/auto-update-policies", repo.id()).header(USER_HEADER, owner)
                    .contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsBytes(rules)))
                    .andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(rules.size()));
        }
        assertThatThrownBy(() -> RestClient.create(System.getenv("LIVINGDOCS_E2E_AI_URL"))
                .get().uri("/internal/revision-draft-candidates/{id}", repo.id()).retrieve().toBodilessEntity())
                .isInstanceOf(org.springframework.web.client.HttpClientErrorException.Unauthorized.class);

        var pushEvent = pushPayload(repo.githubId(), "refs/heads/main", sha);
        String delivery = UUID.randomUUID().toString();
        sendWebhook(pushEvent, delivery).andExpect(status().isAccepted())
                .andExpect(jsonPath("$.status").value("PROCESSED"));
        sendWebhook(pushEvent, delivery).andExpect(status().isAccepted())
                .andExpect(jsonPath("$.status").value("DUPLICATE"));
        UUID repositoryId = UUID.fromString(repo.id());
        if (scenario == Scenario.STAGE_RESTART) {
            await(() -> revisionJdbc.queryForObject("""
                    SELECT count(*) FROM revision_jobs
                    WHERE repository_id = ? AND status = 'QUEUED' AND attempts = 1
                        AND error_code = 'ANALYZER_UNAVAILABLE'
                    """, Integer.class, repositoryId) == 1);
            assertThat(revisionJdbc.update("""
                    UPDATE revision_jobs SET available_at = CURRENT_TIMESTAMP + INTERVAL '1 day'
                    WHERE repository_id = ? AND status = 'QUEUED' AND attempts = 1
                    """, repositoryId)).isEqualTo(1);
            assertThat(analysisCalls.get()).isEqualTo(1);
            assertThat(ai.get().uri("/internal/documents/{id}", documentId).retrieve().body(JsonNode.class)
                    .path("pending_version").isNull()).isTrue();
            return;
        }
        if (scenario == Scenario.REPLACE_WORKER) {
            try {
                assertThat(firstWorker.await(10, TimeUnit.SECONDS)).isTrue();
                assertThat(revisionJdbc.update(
                        "UPDATE revision_jobs SET available_at = CURRENT_TIMESTAMP - INTERVAL '1 second' "
                                + "WHERE repository_id = ? AND status = 'RUNNING'", repositoryId)).isEqualTo(1);
                revisionWorker.poll();
            } finally {
                releaseFirstWorker.countDown();
            }
        }
        await(() -> "COMPLETED".equals(revisionJdbc.queryForObject(
                "SELECT status FROM revision_jobs WHERE repository_id = ?", String.class, repositoryId)));
        assertThat(revisionJdbc.queryForObject("SELECT count(*) FROM revision_jobs WHERE repository_id = ?",
                Integer.class, repositoryId)).isEqualTo(1);
        assertThat(revisionJdbc.queryForObject("SELECT attempts FROM revision_jobs WHERE repository_id = ?",
                Integer.class, repositoryId))
                .isEqualTo(scenario == Scenario.RETRY || scenario == Scenario.REPLACE_WORKER ? 2 : 1);
        var rows = workflowRows.findByOwnerUserIdOrderByCreatedAtDesc(owner, PageRequest.of(0, 10));
        assertThat(rows).hasSize(1);
        assertThat(rows.getContent().getFirst().getId()).isEqualTo(id);
        String docUrl = "/internal/documents/" + documentId;
        var pending = ai.get().uri(docUrl).retrieve().body(JsonNode.class);
        if (scenario == Scenario.POLICY_DISABLED) {
            assertThat(pending.path("pending_version").isNull()).isTrue();
            assertThat(pending.path("current_version").asInt()).isEqualTo(1);
            assertThat(pending.path("versions_total").asInt()).isEqualTo(1);
            return;
        }
        assertThat(pending.path("pending_version").asInt()).isEqualTo(2);
        assertThat(pending.path("current_version").asInt()).isEqualTo(1);
        assertThat(pending.path("pending_revision").path("commit_sha").asText()).isEqualTo(sha);

        assertThatThrownBy(() -> workflows.decide(manager, managerPermissions, id, ManagerDecision.APPROVED, null, 2))
                .hasMessageContaining("successful staff review");
        workflows.claim(staff, staffPermissions, id);
        var comparison = workflows.reviewComparison(staff, staffPermissions, id);
        var revision = comparison.path("pending_version");
        assertThat(revision.path("number").asInt()).isEqualTo(2);
        var snapshot = revision.path("evidence_report");
        assertThat(snapshot.path("template_id").asText()).isEqualTo(templateId);
        assertThat(snapshot.path("template_version").asInt()).isEqualTo(1);
        assertThat(snapshot.path("template_instructions").asText()).isEqualTo("Describe the source.");
        assertThat(snapshot.path("template_sections")).extracting(JsonNode::asText)
                .containsExactly("Overview", "Classes");
        assertThat(revision.path("content").asText()).contains("## Overview", "## Classes")
                .doesNotContain("## API Endpoints");
        boolean staffEdits = scenario == Scenario.APPROVE;
        String staffEditReason = "Clarified the invoice description";
        int reviewedVersion = staffEdits ? 3 : 2;
        EditDocumentRequest staffEdit = null;
        if (staffEdits) {
            String original = revision.path("content").asText();
            var invalid = new EditDocumentRequest(original.replace("## Classes", "## API Endpoints"),
                    staffEditReason, 2);
            assertThatThrownBy(() -> workflows.staffReview(staff, staffPermissions, id,
                    new StaffReviewRequest(StaffReviewResult.PASSED, "Verified against source", invalid)))
                    .hasMessageContaining("template headings");
            assertThat(workflowRows.findById(id).orElseThrow().getSubmittedDocumentVersion()).isEqualTo(2);
            staffEdit = new EditDocumentRequest(original + "\nStaff clarification.\n", staffEditReason, 2);
        }
        workflows.staffReview(staff, staffPermissions, id,
                new StaffReviewRequest(StaffReviewResult.PASSED, "Verified against source", staffEdit));
        assertThatThrownBy(() -> workflows.decide(manager, managerPermissions, id, ManagerDecision.APPROVED, null, 1))
                .hasMessageContaining("Reload the submitted document version");
        when(gitHubClient.getCommit(TOKEN, "acme", "docs", "main"))
                .thenReturn(new GitHubCommit(newSha(), null, null, null));
        assertThatThrownBy(() -> workflows.decide(manager, managerPermissions, id, ManagerDecision.APPROVED, null,
                reviewedVersion))
                .hasMessageContaining("could not be verified as current");
        when(gitHubClient.getCommit(TOKEN, "acme", "docs", "main")).thenReturn(commit);

        boolean reject = scenario == Scenario.REJECT;
        var decision = reject ? ManagerDecision.REJECTED : ManagerDecision.APPROVED;
        String managerReason = reject ? "Needs clarification" : "Verified the reviewed revision";
        workflows.decide(manager, managerPermissions, id, decision, managerReason, reviewedVersion);
        var history = workflows.history(owner, Set.of("DOCUMENT_VIEW"), id).stream()
                .filter(event -> event.documentVersion() != null && event.documentVersion() >= 2)
                .toList();
        assertThat(history).extracting(event -> event.action())
                .containsSubsequence("REVISION_DRAFT_SUBMITTED", "PASSED", decision.name());
        assertThat(history).filteredOn(event -> event.action().equals("REVISION_DRAFT_SUBMITTED"))
                .singleElement().satisfies(event -> assertThat(event.triggerSource()).isEqualTo("COMMIT"));
        assertThat(history).filteredOn(event -> event.action().equals(decision.name()))
                .singleElement().satisfies(event -> assertThat(event.triggerSource()).isEqualTo("REVIEW_WORKFLOW"));
        assertThat(history).allSatisfy(event -> {
            assertThat(event.documentId()).isEqualTo(documentId);
            assertThat(event.createdAt()).isNotNull();
        });
        assertThat(history).anySatisfy(event -> {
            assertThat(event.action()).isEqualTo("REVISION_DRAFT_SUBMITTED");
            assertThat(event.actorUserId()).isEqualTo("AI");
            assertThat(event.actorRole()).isEqualTo("AI");
            assertThat(event.comment()).contains(sha);
        });
        assertThat(history).anySatisfy(event -> {
            assertThat(event.action()).isEqualTo("PASSED");
            assertThat(event.actorUserId()).isEqualTo(staff);
            assertThat(event.actorRole()).isEqualTo("STAFF");
            assertThat(event.comment()).isEqualTo("Verified against source");
            assertThat(event.documentVersion()).isEqualTo(reviewedVersion);
        });
        assertThat(history).anySatisfy(event -> {
            assertThat(event.action()).isEqualTo(decision.name());
            assertThat(event.actorUserId()).isEqualTo(manager);
            assertThat(event.actorRole()).isEqualTo("MANAGER");
            assertThat(event.comment()).isEqualTo(managerReason);
            assertThat(event.documentVersion()).isEqualTo(reviewedVersion);
        });
        assertThat(revision.path("source_changes").get(0).path("commit_sha").asText()).isEqualTo(sha);
        assertThat(revision.path("source_changes").get(0).path("trigger").asText()).isEqualTo("COMMIT");
        var resolved = ai.get().uri(docUrl).retrieve().body(JsonNode.class);
        assertThat(resolved.path("pending_version").isNull()).isTrue();
        assertThat(resolved.path("current_version").asInt()).isEqualTo(reject ? 1 : reviewedVersion);
        assertThat(resolved.path("versions_total").asInt()).isEqualTo(reviewedVersion);
        String visible = ai.get().uri(docUrl + "/content").retrieve().body(String.class);
        if (reject) {
            assertThat(visible).doesNotContain("Calculates invoice totals with tax.");
            assertThatThrownBy(() -> commitBack.commit(manager, managerPermissions, id, 2))
                    .hasMessageContaining("not approved");
        } else {
            assertThat(visible).contains("Calculates invoice totals with tax.");
        }
        if (staffEdits) {
            assertThat(visible).contains("Staff clarification.");
            assertThat(history).extracting(event -> event.action())
                    .containsSubsequence("REVISION_DRAFT_SUBMITTED", "STAFF_DRAFT_EDITED", "PASSED", "APPROVED");
            assertThat(history).anySatisfy(event -> {
                assertThat(event.action()).isEqualTo("STAFF_DRAFT_EDITED");
                assertThat(event.actorUserId()).isEqualTo(staff);
                assertThat(event.actorRole()).isEqualTo("STAFF");
                assertThat(event.documentVersion()).isEqualTo(reviewedVersion);
                assertThat(event.comment()).isEqualTo(staffEditReason);
            });
            var edited = ai.get().uri(docUrl + "/versions/{version}", reviewedVersion)
                    .retrieve().body(JsonNode.class);
            assertThat(edited.path("evidence_from_version").asInt()).isEqualTo(2);
            assertThat(edited.path("source_snapshot").path("commit_sha").asText()).isEqualTo(sha);
            assertCommitBackAudit(manager, managerPermissions, id, repo, documentId, reviewedVersion, sha, visible, owner);
        }
    }

    private void assertCommitBackAudit(String manager, Set<String> permissions, UUID workflowId,
            Repo repo, String documentId, int version, String sourceSha, String content, String owner) throws Exception {
        saveConnection(manager);
        String publishedSha = newSha();
        String treeSha = newSha();
        String path = ".livingdocs/" + documentId + "-v" + version + ".md";
        byte[] bytes = content.getBytes(StandardCharsets.UTF_8);
        when(gitHubClient.getPublicationBranch(TOKEN, "acme", "docs")).thenReturn(
                new GitHubClient.PublicationBranch(repo.githubId(), "acme/docs", "ref", "main", sourceSha, treeSha));
        when(gitHubClient.getTree(TOKEN, "acme", "docs", treeSha))
                .thenReturn(new GitHubTree(treeSha, false, List.of()));
        String message = "Publish LivingDocs document " + documentId + " v" + version;
        when(gitHubClient.commitFileOnBranch(TOKEN, "ref", sourceSha, path, bytes, message))
                .thenReturn(publishedSha);
        assertThat(commitBack.commit(manager, permissions, workflowId, version).observedHeadSha()).isEqualTo(publishedSha);

        var hash = java.security.MessageDigest.getInstance("SHA-1");
        hash.update(("blob " + bytes.length + "\0").getBytes(StandardCharsets.US_ASCII));
        String blob = java.util.HexFormat.of().formatHex(hash.digest(bytes));
        when(gitHubClient.getPublicationBranch(TOKEN, "acme", "docs")).thenReturn(
                new GitHubClient.PublicationBranch(repo.githubId(), "acme/docs", "ref", "main", publishedSha, treeSha));
        when(gitHubClient.getTree(TOKEN, "acme", "docs", treeSha)).thenReturn(new GitHubTree(treeSha, false,
                List.of(new GitHubTree.Entry(path, "100644", "blob", blob, (long) bytes.length))));
        assertThat(commitBack.commit(manager, permissions, workflowId, version).alreadyPresent()).isTrue();
        org.mockito.Mockito.verify(gitHubClient).commitFileOnBranch(TOKEN, "ref", sourceSha, path, bytes, message);
        assertThat(workflows.history(owner, Set.of("DOCUMENT_VIEW"), workflowId))
                .filteredOn(entry -> entry.action().equals("COMMIT_BACK_CONFIRMED"))
                .singleElement().satisfies(entry -> {
                    assertThat(entry.documentId()).isEqualTo(documentId);
                    assertThat(entry.documentVersion()).isEqualTo(version);
                    assertThat(entry.actorUserId()).isEqualTo(manager);
                    assertThat(entry.actorRole()).isEqualTo("MANAGER");
                    assertThat(entry.createdAt()).isNotNull();
                    assertThat(entry.comment()).contains(sourceSha, publishedSha, "Published approved version");
                });
    }

    enum Scenario {
        APPROVE, REJECT, REPLACE_WORKER, RETRY, POLICY_DISABLED, DOCUMENT_OVERRIDE, STAGE_RESTART
    }

    @org.junit.jupiter.api.Test
    @org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable(named = "LIVINGDOCS_E2E_RESTART_PHASE", matches = "stage")
    void stageRetryForProcessRestart() throws Exception {
        signedWebhookRequiresStaffAndExactManagerDecision(Scenario.STAGE_RESTART);
    }

    @org.junit.jupiter.api.Test
    @org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable(named = "LIVINGDOCS_E2E_RESTART_PHASE", matches = "resume")
    void recoversQueuedWebhookAfterBothServicesRestart() throws Exception {
        var job = revisionJdbc.queryForMap("""
                SELECT id, repository_id, commit_sha FROM revision_jobs
                WHERE status = 'QUEUED' AND attempts = 1 AND error_code = 'ANALYZER_UNAVAILABLE'
                """);
        var baseline = revisionJdbc.queryForMap("""
                SELECT id, document_id, owner_user_id FROM document_workflows
                WHERE status = 'APPROVED' AND submitted_document_version = 1
                """);
        UUID repositoryId = (UUID) job.get("repository_id");
        UUID workflowId = (UUID) baseline.get("id");
        String sha = (String) job.get("commit_sha");
        String documentId = (String) baseline.get("document_id");
        String owner = (String) baseline.get("owner_user_id");
        var ai = aiService.mutate().defaultHeader(USER_HEADER, owner).build();
        String docUrl = "/internal/documents/" + documentId;
        assertThat(ai.get().uri(docUrl).retrieve().body(JsonNode.class).path("current_version").asInt()).isEqualTo(1);

        when(gitHubClient.getCommit(TOKEN, "acme", "docs", "main"))
                .thenReturn(new GitHubCommit(sha, null, null, null));
        when(gitHubClient.getCommitFiles(TOKEN, "acme", "docs", sha)).thenReturn(List.of(invoiceFile(PATCH)));
        mockInvoiceContentAndAnalyzer();
        var analysis = json.createObjectNode();
        analysis.putArray("files").addObject().put("path", PATH).put("language", "java")
                .putArray("classes").addObject().put("name", "Invoice").put("lineno", 1)
                .put("docstring", "Includes tax in the total.");
        when(revisionAnalyzer.post().uri("/api/v1/analyze-repo")
                .body(org.mockito.ArgumentMatchers.any(AnalysisInput.class)).retrieve()
                .body(JsonNode.class)).thenReturn(analysis);
        // The first process parked the retry to keep it from running before the restart.
        assertThat(revisionJdbc.update("""
                UPDATE revision_jobs SET available_at = CURRENT_TIMESTAMP
                WHERE id = ? AND repository_id = ? AND status = 'QUEUED' AND attempts = 1
                """, job.get("id"), repositoryId)).isEqualTo(1);
        await(() -> "COMPLETED".equals(revisionJdbc.queryForObject(
                "SELECT status FROM revision_jobs WHERE id = ?", String.class, job.get("id"))));
        assertThat(revisionJdbc.queryForObject("SELECT attempts FROM revision_jobs WHERE id = ?",
                Integer.class, job.get("id"))).isEqualTo(2);
        var pending = ai.get().uri(docUrl).retrieve().body(JsonNode.class);
        assertThat(pending.path("pending_version").asInt()).isEqualTo(2);
        assertThat(pending.path("pending_revision").path("commit_sha").asText()).isEqualTo(sha);
        var staffPermissions = Set.of("ROLE_STAFF", "DOCUMENT_CLAIM", "DOCUMENT_REVIEW");
        workflows.claim("revision-staff", staffPermissions, workflowId);
        workflows.staffReview("revision-staff", staffPermissions, workflowId,
                new StaffReviewRequest(StaffReviewResult.PASSED, "Verified after restart"));
        workflows.decide("revision-manager", Set.of("ROLE_MANAGER", "DOCUMENT_APPROVE"),
                workflowId, ManagerDecision.APPROVED, null, 2);
        var published = ai.get().uri(docUrl).retrieve().body(JsonNode.class);
        assertThat(published.path("current_version").asInt()).isEqualTo(2);
        assertThat(published.path("versions_total").asInt()).isEqualTo(2);
    }

    private static void await(java.util.function.BooleanSupplier condition) throws InterruptedException {
        long deadline = System.nanoTime() + Duration.ofSeconds(30).toNanos();
        while (!condition.getAsBoolean()) {
            assertThat(System.nanoTime()).as("integration condition before timeout").isLessThan(deadline);
            Thread.sleep(100);
        }
    }


    private void mockInvoiceContentAndAnalyzer() {
        when(gitHubClient.getBlob(TOKEN, "acme", "docs", BLOB)).thenReturn(blob(AFTER));
        when(analyzerClient.analyze(eq("acme/docs"), anyList())).thenAnswer(this::analyzeInvoice);
    }

    private Map<String, List<CodeEntity>> analyzeInvoice(InvocationOnMock call) {
        List<AnalysisInput.FileInput> files = call.getArgument(1);
        Map<String, List<CodeEntity>> result = new HashMap<>();
        for (AnalysisInput.FileInput file : files) {
            boolean after = file.content().contains("tax()");
            if (!after) {
                assertThat(file.content()).isEqualTo(BEFORE); // dựng lại đúng từ nội dung sau + patch
            }
            result.put(file.path(), List.of(new CodeEntity("CLASS", "Invoice", 1, 9),
                    new CodeEntity("METHOD", "Invoice.total", 2, 4),
                    new CodeEntity("METHOD", after ? "Invoice.tax" : "Invoice.discount", 6, 8)));
        }
        return result;
    }

    private static GitHubChangedFile invoiceFile(String patch) {
        return new GitHubChangedFile(PATH, "modified", null, BLOB, 4, 4, patch);
    }

    private static GitHubBlob blob(String content) {
        return new GitHubBlob(BLOB, (long) content.length(), "base64",
                Base64.getEncoder().encodeToString(content.getBytes(StandardCharsets.UTF_8)));
    }


    private org.springframework.test.web.servlet.ResultActions sendWebhook(Map<String, Object> payload, String delivery)
            throws Exception {
        byte[] body = json.writeValueAsBytes(payload);
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(WEBHOOK_SECRET.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        return mvc.perform(post("/api/github/webhook")
                .header("X-GitHub-Event", "push")
                .header("X-GitHub-Delivery", delivery)
                .header("X-Hub-Signature-256", "sha256=" + java.util.HexFormat.of().formatHex(mac.doFinal(body)))
                .contentType(MediaType.APPLICATION_JSON)
                .content(body));
    }

    private static Map<String, Object> pushPayload(long githubRepoId, String ref, String sha) {
        return Map.of("ref", ref, "deleted", false,
                "repository", Map.of("id", githubRepoId, "full_name", "acme/docs"),
                "commits", List.of(Map.of("id", sha, "message", "Update invoice", "timestamp", "2026-11-06T10:00:00+07:00",
                        "url", "https://github.com/acme/docs/commit/" + sha,
                        "author", Map.of("name", "Hai Dang", "username", "d3r-bbb"))));
    }


    private record Repo(String id, long githubId) {
    }

    private void saveConnection(String user) {
        GitHubConnection connection = new GitHubConnection();
        connection.setUserId(user);
        connection.setGithubUserId(9200L);
        connection.setGithubLogin("d3r-bbb");
        connection.setAccessToken(TOKEN);
        connection.setAccessTokenExpiresAt(Instant.now().plus(Duration.ofHours(8)));
        connection.setStatus(ConnectionStatus.ACTIVE);
        connectionRepository.save(connection);
    }

    private Repo connectAndAddRepo(String user) throws Exception {
        saveConnection(user);
        return addRepo(user);
    }

    private Repo addRepo(String user) throws Exception {
        long githubId = NEXT_GITHUB_REPO_ID.incrementAndGet();
        GitHubRepo docs = new GitHubRepo(githubId, "acme/docs", false, "main", "https://github.com/acme/docs");
        when(gitHubClient.listUserRepositories(TOKEN)).thenReturn(List.of(docs));
        String body = mvc.perform(post("/api/workspaces/ws-" + user + "/repositories").header(USER_HEADER, user)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"githubRepoIds\":[" + githubId + "]}"))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        return new Repo(json.readTree(body).get(0).get("id").asText(), githubId);
    }

    private static String newSha() {
        return UUID.randomUUID().toString().replace("-", "") + "00000000";
    }


}
