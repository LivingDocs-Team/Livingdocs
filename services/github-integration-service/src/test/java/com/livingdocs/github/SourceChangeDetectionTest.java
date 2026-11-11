package com.livingdocs.github;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.change.AffectedDocumentsClient;
import com.livingdocs.github.change.CodeAnalyzerClient;
import com.livingdocs.github.change.CodeEntity;
import com.livingdocs.github.change.SourceChangeException;
import com.livingdocs.github.change.SourceChangeRequest;
import com.livingdocs.github.client.GitHubBlob;
import com.livingdocs.github.client.GitHubChangedFile;
import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.client.GitHubRepo;
import com.livingdocs.github.entity.ConnectionStatus;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.entity.SourceChange;
import com.livingdocs.github.exception.GitHubApiException;
import com.livingdocs.github.repository.GitHubConnectionRepository;
import com.livingdocs.github.service.SourceChangeService;
import com.livingdocs.github.sync.AnalysisInput;
import org.junit.jupiter.api.Test;
import org.mockito.invocation.InvocationOnMock;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
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
import java.util.concurrent.atomic.AtomicLong;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.contains;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.after;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * LD-121: phát hiện thay đổi mã nguồn (LD-116) với database H2, GitHub và Code Analyzer giả.
 * Mỗi test dùng user và workspace riêng vì database được dùng chung giữa các class test.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(com.livingdocs.github.security.InternalServiceTestMvcConfig.class)
class SourceChangeDetectionTest {

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
    @Autowired SourceChangeService sourceChangeService;

    @MockitoBean GitHubClient gitHubClient;
    @MockitoBean CodeAnalyzerClient analyzerClient;
    @MockitoBean AffectedDocumentsClient documentsClient;  // trả danh sách rỗng nếu test không cấu hình

    // ------------------------------------------------------------------ LD-118: commit trên nhánh mặc định

    @Test
    void commitOnDefaultBranch_isDetectedAfterWebhook_withChangedEntities() throws Exception {
        String user = "change-commit";
        Repo repo = connectAndAddRepo(user);
        String sha = newSha();
        when(gitHubClient.getCommitFiles(TOKEN, "acme", "docs", sha)).thenReturn(List.of(invoiceFile(PATCH), readmeFile()));
        mockInvoiceContentAndAnalyzer();

        sendWebhook("push", pushPayload(repo.githubId(), "refs/heads/main", sha)).andExpect(jsonPath("$.status").value("PROCESSED"));
        waitForSourceChanges(repo.id(), user, 1);

        mvc.perform(get(sourceChangesUrl(repo.id())).header(USER_HEADER, user))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].trigger").value("COMMIT"))
                .andExpect(jsonPath("$[0].commitSha").value(sha))
                .andExpect(jsonPath("$[0].status").value("PENDING"))
                .andExpect(jsonPath("$[0].files.length()").value(1))  // README.md không phải mã nguồn
                .andExpect(jsonPath("$[0].files[0].path").value(PATH))
                .andExpect(jsonPath("$[0].files[0].change").value("MODIFIED"))
                .andExpect(jsonPath("$[0].files[0].language").value("java"))
                .andExpect(jsonPath("$[0].files[0].skippedReason").doesNotExist())
                .andExpect(jsonPath("$[0].files[0].entities.length()").value(4))
                .andExpect(jsonPath("$[0].files[0].entities[?(@.name == 'Invoice')].change", contains("MODIFIED")))
                .andExpect(jsonPath("$[0].files[0].entities[?(@.name == 'Invoice.total')].change", contains("MODIFIED")))
                .andExpect(jsonPath("$[0].files[0].entities[?(@.name == 'Invoice.tax')].change", contains("ADDED")))
                .andExpect(jsonPath("$[0].files[0].entities[?(@.name == 'Invoice.discount')].change", contains("REMOVED")));
    }

    @Test
    void commitOnOtherBranch_isStoredButNotDetected() throws Exception {
        String user = "change-feature-branch";
        Repo repo = connectAndAddRepo(user);
        String sha = newSha();

        sendWebhook("push", pushPayload(repo.githubId(), "refs/heads/feature/invoices", sha))
                .andExpect(jsonPath("$.status").value("PROCESSED"));

        verify(gitHubClient, after(1000).never()).getCommitFiles(anyString(), anyString(), anyString(), eq(sha));
        mvc.perform(get(sourceChangesUrl(repo.id())).header(USER_HEADER, user))
                .andExpect(jsonPath("$.length()").value(0));
    }

    // ------------------------------------------------------------------ LD-119: Pull Request

    @Test
    void openPullRequestWithNewHead_isDetected_closingItIsNot() throws Exception {
        String user = "change-pull-request";
        Repo repo = connectAndAddRepo(user);
        String head = newSha();
        when(gitHubClient.listPullRequestChangedFiles(TOKEN, "acme", "docs", 12)).thenReturn(List.of(invoiceFile(PATCH)));
        mockInvoiceContentAndAnalyzer();

        sendWebhook("pull_request", pullRequestPayload(repo.githubId(), "opened", 12, "open", head, "2026-11-06T03:00:00Z"))
                .andExpect(jsonPath("$.status").value("PROCESSED"));
        waitForSourceChanges(repo.id(), user, 1);
        sendWebhook("pull_request", pullRequestPayload(repo.githubId(), "closed", 12, "closed", head, "2026-11-06T04:00:00Z"))
                .andExpect(jsonPath("$.status").value("PROCESSED"));

        verify(gitHubClient, after(1000).times(1)).listPullRequestChangedFiles(TOKEN, "acme", "docs", 12);
        mvc.perform(get(sourceChangesUrl(repo.id())).header(USER_HEADER, user))
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].trigger").value("PULL_REQUEST"))
                .andExpect(jsonPath("$[0].pullRequestNumber").value(12))
                .andExpect(jsonPath("$[0].commitSha").value(head))
                .andExpect(jsonPath("$[0].files[0].entities[?(@.name == 'Invoice.tax')].change", contains("ADDED")));
    }

    // ------------------------------------------------------------------ Không có mã nguồn, lỗi, thử lại

    @Test
    void commitWithoutSourceFiles_isNotStored() throws Exception {
        String user = "change-docs-only";
        Repo repo = connectAndAddRepo(user);
        String sha = newSha();
        when(gitHubClient.getCommitFiles(TOKEN, "acme", "docs", sha)).thenReturn(List.of(readmeFile()));

        sourceChangeService.detect(commit(repo.id(), sha));

        mvc.perform(get(sourceChangesUrl(repo.id())).header(USER_HEADER, user))
                .andExpect(jsonPath("$.length()").value(0));
        verify(analyzerClient, never()).analyze(eq("acme/docs"), anyList());
    }

    @Test
    void gitHubErrorIsStoredAsFailed_andRetryDetectsAgain() throws Exception {
        String user = "change-retry";
        Repo repo = connectAndAddRepo(user);
        String sha = newSha();
        when(gitHubClient.getCommitFiles(TOKEN, "acme", "docs", sha))
                .thenThrow(new GitHubApiException("GitHub API returned HTTP 503.", 503, new HttpHeaders(), "{}"))
                .thenReturn(List.of(invoiceFile(PATCH)));
        mockInvoiceContentAndAnalyzer();

        sourceChangeService.detect(commit(repo.id(), sha));

        String body = mvc.perform(get(sourceChangesUrl(repo.id())).header(USER_HEADER, user))
                .andExpect(jsonPath("$[0].status").value("FAILED"))
                .andExpect(jsonPath("$[0].errorCode").value("GITHUB_UNAVAILABLE"))
                .andExpect(jsonPath("$[0].files.length()").value(0))
                .andReturn().getResponse().getContentAsString();
        String changeId = json.readTree(body).get(0).get("id").asText();

        mvc.perform(post(sourceChangesUrl(repo.id()) + "/" + changeId + "/retry").header(USER_HEADER, user))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(changeId))
                .andExpect(jsonPath("$.status").value("PENDING"))
                .andExpect(jsonPath("$.errorCode").doesNotExist())
                .andExpect(jsonPath("$.files[0].entities.length()").value(4));
        // Chỉ chạy lại được source change FAILED
        mvc.perform(post(sourceChangesUrl(repo.id()) + "/" + changeId + "/retry").header(USER_HEADER, user))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("SOURCE_CHANGE_NOT_FAILED"));
    }

    @Test
    void analyzerUnavailable_isStoredAsFailed() throws Exception {
        String user = "change-analyzer-down";
        Repo repo = connectAndAddRepo(user);
        String sha = newSha();
        when(gitHubClient.getCommitFiles(TOKEN, "acme", "docs", sha)).thenReturn(List.of(invoiceFile(PATCH)));
        when(gitHubClient.getBlob(TOKEN, "acme", "docs", BLOB)).thenReturn(blob(AFTER));
        when(analyzerClient.analyze(eq("acme/docs"), anyList()))
                .thenThrow(new SourceChangeException("ANALYZER_UNAVAILABLE", "The code analyzer could not analyze the changed files."));

        sourceChangeService.detect(commit(repo.id(), sha));

        mvc.perform(get(sourceChangesUrl(repo.id())).header(USER_HEADER, user))
                .andExpect(jsonPath("$[0].status").value("FAILED"))
                .andExpect(jsonPath("$[0].errorCode").value("ANALYZER_UNAVAILABLE"));
    }

    @Test
    void fileWithoutPatch_isListedWithoutEntities() throws Exception {
        String user = "change-no-patch";
        Repo repo = connectAndAddRepo(user);
        String sha = newSha();
        when(gitHubClient.getCommitFiles(TOKEN, "acme", "docs", sha)).thenReturn(List.of(invoiceFile(null)));

        sourceChangeService.detect(commit(repo.id(), sha));

        mvc.perform(get(sourceChangesUrl(repo.id())).header(USER_HEADER, user))
                .andExpect(jsonPath("$[0].status").value("PENDING"))
                .andExpect(jsonPath("$[0].files[0].skippedReason").value("PATCH_UNAVAILABLE"))
                .andExpect(jsonPath("$[0].files[0].entities.length()").value(0));
        verify(gitHubClient, never()).getBlob(anyString(), anyString(), anyString(), eq(BLOB));
    }

    // ------------------------------------------------------------------ LD-122: tài liệu bị ảnh hưởng (LD-127)

    @Test
    void affectedDocumentsAreStoredWithTheSourceChange_directFirst() throws Exception {
        String user = "change-affected-docs";
        Repo repo = connectAndAddRepo(user);
        String sha = newSha();
        when(gitHubClient.getCommitFiles(TOKEN, "acme", "docs", sha)).thenReturn(List.of(invoiceFile(PATCH)));
        mockInvoiceContentAndAnalyzer();
        when(documentsClient.find(eq("acme/docs"), anyList())).thenReturn(List.of(
                new AffectedDocumentsClient.Affected("doc-1", "Billing docs", 3, "src/main/java/acme/Checkout.java",
                        "src/main/java/acme/Checkout.java", "dependent", List.of("mentions `Invoice.total`")),
                new AffectedDocumentsClient.Affected("doc-1", "Billing docs", 3, PATH, PATH, "direct",
                        List.of("documents changed file " + PATH, "mentions `Invoice.discount`"))));

        sourceChangeService.detect(commit(repo.id(), sha));

        mvc.perform(get(sourceChangesUrl(repo.id())).header(USER_HEADER, user))
                .andExpect(jsonPath("$[0].status").value("PENDING"))
                .andExpect(jsonPath("$[0].documentsStatus").value("FOUND"))
                .andExpect(jsonPath("$[0].documentsErrorCode").doesNotExist())
                .andExpect(jsonPath("$[0].affectedDocuments.length()").value(2))
                .andExpect(jsonPath("$[0].affectedDocuments[0].dependency").value("DIRECT"))
                .andExpect(jsonPath("$[0].affectedDocuments[0].documentId").value("doc-1"))
                .andExpect(jsonPath("$[0].affectedDocuments[0].title").value("Billing docs"))
                .andExpect(jsonPath("$[0].affectedDocuments[0].version").value(3))
                .andExpect(jsonPath("$[0].affectedDocuments[0].section").value(PATH))
                .andExpect(jsonPath("$[0].affectedDocuments[0].reasons[0]").value("documents changed file " + PATH))
                .andExpect(jsonPath("$[0].affectedDocuments[0].reasons[1]").value("mentions `Invoice.discount`"))
                .andExpect(jsonPath("$[0].affectedDocuments[1].dependency").value("DEPENDENT"))
                .andExpect(jsonPath("$[0].affectedDocuments[1].section").value("src/main/java/acme/Checkout.java"));

        // ai-service nhận đúng file và code entity mà LD-116 đã tìm
        verify(documentsClient).find(eq("acme/docs"), argThat(files -> files.size() == 1
                && files.get(0).path().equals(PATH) && files.get(0).change().equals("MODIFIED")
                && files.get(0).entities().contains(
                        new AffectedDocumentsClient.ChangedEntity("METHOD", "Invoice.tax", "ADDED"))
                && files.get(0).entities().contains(
                        new AffectedDocumentsClient.ChangedEntity("METHOD", "Invoice.discount", "REMOVED"))));
    }

    @Test
    void aiServiceError_isStoredAsDocumentsFailed_andRetryChecksOnlyTheDocumentsAgain() throws Exception {
        String user = "change-docs-retry";
        Repo repo = connectAndAddRepo(user);
        String sha = newSha();
        when(gitHubClient.getCommitFiles(TOKEN, "acme", "docs", sha)).thenReturn(List.of(invoiceFile(PATCH)));
        mockInvoiceContentAndAnalyzer();
        when(documentsClient.find(eq("acme/docs"), anyList()))
                .thenThrow(new SourceChangeException("AI_SERVICE_UNAVAILABLE", "The AI service is down."))
                .thenReturn(List.of(new AffectedDocumentsClient.Affected("doc-2", "Docs", 1, PATH, PATH, "direct",
                        List.of("documents changed file " + PATH))));

        sourceChangeService.detect(commit(repo.id(), sha));

        String body = mvc.perform(get(sourceChangesUrl(repo.id())).header(USER_HEADER, user))
                .andExpect(jsonPath("$[0].status").value("PENDING"))  // phát hiện thay đổi vẫn thành công
                .andExpect(jsonPath("$[0].files[0].entities.length()").value(4))
                .andExpect(jsonPath("$[0].documentsStatus").value("FAILED"))
                .andExpect(jsonPath("$[0].documentsErrorCode").value("AI_SERVICE_UNAVAILABLE"))
                .andExpect(jsonPath("$[0].affectedDocuments.length()").value(0))
                .andReturn().getResponse().getContentAsString();
        String changeId = json.readTree(body).get(0).get("id").asText();

        mvc.perform(post(sourceChangesUrl(repo.id()) + "/" + changeId + "/retry").header(USER_HEADER, user))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.documentsStatus").value("FOUND"))
                .andExpect(jsonPath("$.documentsErrorCode").doesNotExist())
                .andExpect(jsonPath("$.affectedDocuments[0].documentId").value("doc-2"))
                .andExpect(jsonPath("$.files[0].entities.length()").value(4));
        verify(gitHubClient, times(1)).getCommitFiles(TOKEN, "acme", "docs", sha);  // không phát hiện lại

        mvc.perform(post(sourceChangesUrl(repo.id()) + "/" + changeId + "/retry").header(USER_HEADER, user))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("SOURCE_CHANGE_NOT_FAILED"));
    }

    @Test
    void failedSourceChange_hasNoDocumentsStep() throws Exception {
        String user = "change-failed-no-docs";
        Repo repo = connectAndAddRepo(user);
        String sha = newSha();
        when(gitHubClient.getCommitFiles(TOKEN, "acme", "docs", sha))
                .thenThrow(new GitHubApiException("GitHub API returned HTTP 503.", 503, new HttpHeaders(), "{}"));

        sourceChangeService.detect(commit(repo.id(), sha));

        mvc.perform(get(sourceChangesUrl(repo.id())).header(USER_HEADER, user))
                .andExpect(jsonPath("$[0].status").value("FAILED"))
                .andExpect(jsonPath("$[0].documentsStatus").doesNotExist())
                .andExpect(jsonPath("$[0].affectedDocuments.length()").value(0));
        verify(documentsClient, never()).find(anyString(), anyList());
    }

    @Test
    void otherUserCannotSeeOrRetrySourceChanges() throws Exception {
        Repo repo = connectAndAddRepo("change-owner");

        mvc.perform(get(sourceChangesUrl(repo.id())).header(USER_HEADER, "change-stranger"))
                .andExpect(status().isForbidden());
        mvc.perform(post(sourceChangesUrl(repo.id()) + "/" + UUID.randomUUID() + "/retry").header(USER_HEADER, "change-stranger"))
                .andExpect(status().isForbidden());
        mvc.perform(post(sourceChangesUrl(repo.id()) + "/" + UUID.randomUUID() + "/retry").header(USER_HEADER, "change-owner"))
                .andExpect(status().isNotFound());
    }

    // ------------------------------------------------------------------ helpers

    /** Nội dung Invoice.java sau thay đổi, và analyzer giả: bản sau có tax(), bản trước có discount(). */
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

    private static GitHubChangedFile readmeFile() {
        return new GitHubChangedFile("README.md", "modified", null, "d4".repeat(20), 1, 0, "@@ -1 +1,2 @@\n # Docs\n+More");
    }

    private static GitHubBlob blob(String content) {
        return new GitHubBlob(BLOB, (long) content.length(), "base64",
                Base64.getEncoder().encodeToString(content.getBytes(StandardCharsets.UTF_8)));
    }

    private static SourceChangeRequest commit(String repoId, String sha) {
        return new SourceChangeRequest(UUID.fromString(repoId), SourceChange.Trigger.COMMIT, sha, null);
    }

    /** Chờ bước phát hiện chạy nền sau webhook (tối đa 5 giây). */
    private void waitForSourceChanges(String repoId, String user, int expected) throws Exception {
        for (int i = 0; i < 50; i++) {
            String body = mvc.perform(get(sourceChangesUrl(repoId)).header(USER_HEADER, user))
                    .andExpect(status().isOk())
                    .andReturn().getResponse().getContentAsString();
            if (json.readTree(body).size() >= expected) {
                return;
            }
            Thread.sleep(100);
        }
        throw new AssertionError("Source change was not detected within 5 seconds");
    }

    private org.springframework.test.web.servlet.ResultActions sendWebhook(String event, Map<String, Object> payload)
            throws Exception {
        byte[] body = json.writeValueAsBytes(payload);
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(WEBHOOK_SECRET.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        return mvc.perform(post("/api/github/webhook")
                .header("X-GitHub-Event", event)
                .header("X-GitHub-Delivery", UUID.randomUUID().toString())
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

    private static Map<String, Object> pullRequestPayload(long githubRepoId, String action, int number, String state,
                                                          String head, String updatedAt) {
        Map<String, Object> pr = new HashMap<>();
        pr.put("number", number);
        pr.put("title", "Add tax");
        pr.put("state", state);
        pr.put("html_url", "https://github.com/acme/docs/pull/" + number);
        pr.put("user", Map.of("login", "d3r-bbb"));
        pr.put("head", Map.of("ref", "feature/tax", "sha", head));
        pr.put("base", Map.of("ref", "main", "sha", "e1".repeat(20)));
        pr.put("created_at", "2026-11-06T03:00:00Z");
        pr.put("updated_at", updatedAt);
        return Map.of("action", action, "number", number, "pull_request", pr,
                "repository", Map.of("id", githubRepoId, "full_name", "acme/docs"));
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
        when(gitHubClient.listAccessibleRepositories(TOKEN)).thenReturn(List.of(docs));
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

    private static String sourceChangesUrl(String repoId) {
        return "/api/repositories/" + repoId + "/source-changes";
    }
}
