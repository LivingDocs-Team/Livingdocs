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
import com.livingdocs.github.client.GitHubCommit;
import com.fasterxml.jackson.databind.JsonNode;
import com.livingdocs.github.change.CodeAnalyzerClient;
import com.livingdocs.github.change.CodeEntity;
import com.livingdocs.github.client.GitHubBlob;
import com.livingdocs.github.client.GitHubChangedFile;
import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.client.GitHubRepo;
import com.livingdocs.github.client.GitHubPullRequest;
import com.livingdocs.github.entity.ConnectionStatus;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.repository.GitHubConnectionRepository;
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
    @Autowired GitHubConnectionRepository connectionRepository;
    @Autowired DocumentWorkflowService workflows;
    @Autowired DocumentWorkflowRepository workflowRows;
    @Autowired org.springframework.jdbc.core.JdbcTemplate revisionJdbc;
    @Autowired com.livingdocs.github.change.RevisionJobWorker revisionWorker;
    @Autowired @org.springframework.beans.factory.annotation.Qualifier("aiServiceRestClient")
    RestClient aiService;

    @MockitoBean GitHubClient gitHubClient;
    @MockitoBean CodeAnalyzerClient analyzerClient;
    @MockitoBean(name = "codeAnalyzerRestClient", answers = org.mockito.Answers.RETURNS_DEEP_STUBS)
    RestClient revisionAnalyzer;

    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.ValueSource(strings = {"accept", "edit", "dismiss"})
    @org.junit.jupiter.api.condition.DisabledIfEnvironmentVariable(named = "LIVINGDOCS_E2E_RESTART_PHASE", matches = ".+")
    void driftDecisionUsesRealAiHttpAndExactReviewVersion(String decision) throws Exception {
        String owner = Long.toString(java.util.concurrent.ThreadLocalRandom.current().nextLong(1, Long.MAX_VALUE));
        var repo = connectAndAddRepo(owner);
        var ai = aiService.mutate().defaultHeader(USER_HEADER, owner).build();
        String base = newSha(), head = newSha();
        var previousFile = Map.of("path", PATH, "language", "java",
                "classes", List.of(Map.of("name", "Invoice", "lineno", 1)));
        var job = ai.post().uri("/generate").contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("scope", "file", "target", PATH, "output_language", "en",
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
                "decision", decision, "note", "Reviewed drift", "proposed", "## Receipt"));
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
        workflows.staffReview("staff", staff, workflow, new StaffReviewRequest(StaffReviewResult.PASSED, null));
        assertThatThrownBy(() -> workflows.decide("manager", manager, workflow, ManagerDecision.APPROVED, null, 1))
                .isInstanceOf(com.livingdocs.github.exception.ApiException.class);
        workflows.decide("manager", manager, workflow, ManagerDecision.APPROVED, null, 2);
        assertThat(ai.get().uri("/internal/documents/{id}", documentId).retrieve().body(JsonNode.class)
                .path("current_version").asInt()).isEqualTo(2);
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
        var job = ai.post().uri("/generate").contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("scope", "file", "target", PATH,
                "output_language", "en", "files", List.of(analysis), "source_snapshot",
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

        var event = pushPayload(repo.githubId(), "refs/heads/main", sha);
        String delivery = UUID.randomUUID().toString();
        sendWebhook(event, delivery).andExpect(status().isAccepted())
                .andExpect(jsonPath("$.status").value("PROCESSED"));
        sendWebhook(event, delivery).andExpect(status().isAccepted())
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
        workflows.staffReview(staff, staffPermissions, id,
                new StaffReviewRequest(StaffReviewResult.PASSED, "Verified against source"));
        assertThatThrownBy(() -> workflows.decide(manager, managerPermissions, id, ManagerDecision.APPROVED, null, 1))
                .hasMessageContaining("Reload the submitted document version");
        when(gitHubClient.getCommit(TOKEN, "acme", "docs", "main"))
                .thenReturn(new GitHubCommit(newSha(), null, null, null));
        assertThatThrownBy(() -> workflows.decide(manager, managerPermissions, id, ManagerDecision.APPROVED, null, 2))
                .hasMessageContaining("could not be verified as current");
        when(gitHubClient.getCommit(TOKEN, "acme", "docs", "main")).thenReturn(commit);

        boolean reject = scenario == Scenario.REJECT;
        var decision = reject ? ManagerDecision.REJECTED : ManagerDecision.APPROVED;
        workflows.decide(manager, managerPermissions, id, decision, reject ? "Needs clarification" : null, 2);
        var resolved = ai.get().uri(docUrl).retrieve().body(JsonNode.class);
        assertThat(resolved.path("pending_version").isNull()).isTrue();
        assertThat(resolved.path("current_version").asInt()).isEqualTo(reject ? 1 : 2);
        assertThat(resolved.path("versions_total").asInt()).isEqualTo(2);
        String visible = ai.get().uri(docUrl + "/content").retrieve().body(String.class);
        if (reject) {
            assertThat(visible).doesNotContain("Calculates invoice totals with tax.");
        } else {
            assertThat(visible).contains("Calculates invoice totals with tax.");
        }
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

    private Repo connectAndAddRepo(String user) throws Exception {
        GitHubConnection connection = new GitHubConnection();
        connection.setUserId(user);
        connection.setGithubUserId(9200L);
        connection.setGithubLogin("d3r-bbb");
        connection.setAccessToken(TOKEN);
        connection.setAccessTokenExpiresAt(Instant.now().plus(Duration.ofHours(8)));
        connection.setStatus(ConnectionStatus.ACTIVE);
        connectionRepository.save(connection);

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
