package com.livingdocs.github;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.client.GitHubBlob;
import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.client.GitHubCommit;
import com.livingdocs.github.client.GitHubPullRequest;
import com.livingdocs.github.client.GitHubRepo;
import com.livingdocs.github.client.GitHubRepoDetails;
import com.livingdocs.github.client.GitHubTree;
import com.livingdocs.github.entity.ConnectionStatus;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.exception.GitHubApiException;
import com.livingdocs.github.repository.GitHubConnectionRepository;
import com.livingdocs.github.repository.RepositoryCommitRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * LD-73: nhận Pull Request và commit (LD-68) qua webhook và khi đồng bộ, với database H2 và GitHub giả.
 * Không import InternalServiceTestMvcConfig: webhook phải đi qua mà không cần credential nội bộ,
 * các API khác tự gắn credential bằng {@link #asUser}.
 * Mỗi test dùng user và workspace riêng vì database được dùng chung giữa các class test.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class GitHubWebhookIngestionTest {

    private static final String WEBHOOK = "/api/github/webhook";
    private static final String WEBHOOK_SECRET = "test-only-webhook-secret"; // application-test.yml
    private static final String USER_HEADER = "X-User-Id";
    private static final String INTERNAL_AUTH = "Bearer test-only-internal-credential";
    private static final String TOKEN = "ghu_ingestion_token";
    private static final String SHA_1 = "e5".repeat(20);
    private static final String SHA_2 = "f6".repeat(20);
    private static final String TREE = "a7".repeat(20);
    private static final String APP_SHA = "b8".repeat(20);
    private static final String APP_CODE = "public class Invoice {\n}\n";
    private static final GitHubRepo BILLING =
            new GitHubRepo(5151L, "acme/billing", false, "main", "https://github.com/acme/billing");

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired GitHubConnectionRepository connectionRepository;
    @Autowired RepositoryCommitRepository commitRepository;

    @MockitoBean GitHubClient gitHubClient;

    // ------------------------------------------------------------------ LD-70: commit qua webhook push

    @Test
    void push_storesCommitsOfConnectedRepository() throws Exception {
        String repoId = connectAndAddRepo("ingest-push");

        sendWebhook("push", newDelivery(), pushPayload(BILLING.id(), "refs/heads/main", SHA_1, SHA_2))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.status").value("PROCESSED"));

        mvc.perform(asUser(get(commitsUrl(repoId)), "ingest-push"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2))
                .andExpect(jsonPath("$[0].sha").value(SHA_2))  // mới nhất trước
                .andExpect(jsonPath("$[0].branch").value("main"))
                .andExpect(jsonPath("$[0].message").value("Commit 2"))
                .andExpect(jsonPath("$[0].authorName").value("Hai Dang"))
                .andExpect(jsonPath("$[0].authorLogin").value("d3r-bbb"))
                .andExpect(jsonPath("$[0].committedAt").value("2026-11-06T03:01:00Z"))
                .andExpect(jsonPath("$[0].source").value("WEBHOOK"))
                .andExpect(jsonPath("$[1].sha").value(SHA_1));
    }

    @Test
    void sameDeliveryIsProcessedOnce_andSameCommitIsStoredOnce() throws Exception {
        String repoId = connectAndAddRepo("ingest-duplicate");
        String delivery = newDelivery();
        Map<String, Object> payload = pushPayload(BILLING.id(), "refs/heads/main", SHA_1);

        sendWebhook("push", delivery, payload).andExpect(jsonPath("$.status").value("PROCESSED"));
        // GitHub gửi lại cùng delivery
        sendWebhook("push", delivery, payload)
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.status").value("DUPLICATE"));
        // Delivery khác nhưng cùng commit (ví dụ commit được đẩy thêm lên nhánh khác)
        sendWebhook("push", newDelivery(), pushPayload(BILLING.id(), "refs/heads/release", SHA_1))
                .andExpect(jsonPath("$.status").value("PROCESSED"));

        mvc.perform(asUser(get(commitsUrl(repoId)), "ingest-duplicate"))
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].branch").value("main"));
    }

    // ------------------------------------------------------------------ LD-69: Pull Request qua webhook

    @Test
    void pullRequestIsUpdatedInPlace_andOlderEventDoesNotOverwriteNewerData() throws Exception {
        String repoId = connectAndAddRepo("ingest-pr");

        sendWebhook("pull_request", newDelivery(),
                pullRequestPayload("opened", 7, "open", "2026-11-06T03:00:00Z", null))
                .andExpect(jsonPath("$.status").value("PROCESSED"));
        sendWebhook("pull_request", newDelivery(),
                pullRequestPayload("closed", 7, "closed", "2026-11-06T05:00:00Z", "2026-11-06T05:00:00Z"))
                .andExpect(jsonPath("$.status").value("PROCESSED"));
        // Event cũ hơn đến muộn
        sendWebhook("pull_request", newDelivery(),
                pullRequestPayload("synchronize", 7, "open", "2026-11-06T04:00:00Z", null))
                .andExpect(jsonPath("$.status").value("PROCESSED"));

        mvc.perform(asUser(get(pullRequestsUrl(repoId)), "ingest-pr"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].number").value(7))
                .andExpect(jsonPath("$[0].title").value("Add invoices"))
                .andExpect(jsonPath("$[0].state").value("closed"))
                .andExpect(jsonPath("$[0].merged").value(true))
                .andExpect(jsonPath("$[0].authorLogin").value("d3r-bbb"))
                .andExpect(jsonPath("$[0].headRef").value("feature/invoices"))
                .andExpect(jsonPath("$[0].baseRef").value("main"))
                .andExpect(jsonPath("$[0].source").value("WEBHOOK"));
    }

    // ------------------------------------------------------------------ Chữ ký, event bị bỏ qua

    @Test
    void missingOrWrongSignature_isRejected_andNothingIsStored() throws Exception {
        String repoId = connectAndAddRepo("ingest-signature");
        byte[] body = json.writeValueAsBytes(pushPayload(BILLING.id(), "refs/heads/main", SHA_1));

        mvc.perform(post(WEBHOOK).header("X-GitHub-Event", "push").header("X-GitHub-Delivery", newDelivery())
                        .header("X-Hub-Signature-256", "sha256=" + "00".repeat(32))
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("WEBHOOK_SIGNATURE_INVALID"));
        mvc.perform(post(WEBHOOK).header("X-GitHub-Event", "push").header("X-GitHub-Delivery", newDelivery())
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isUnauthorized());

        mvc.perform(asUser(get(commitsUrl(repoId)), "ingest-signature"))
                .andExpect(jsonPath("$.length()").value(0));
    }

    @Test
    void malformedJson_isRejectedWith400_andDoesNotUseUpTheDelivery() throws Exception {
        String repoId = connectAndAddRepo("ingest-malformed");
        String delivery = newDelivery();
        byte[] broken = "{\"ref\": \"refs/heads/main\", \"commits\": [".getBytes(StandardCharsets.UTF_8);

        // Chữ ký đúng nhưng JSON hỏng: 400, không phải 500
        mvc.perform(post(WEBHOOK).header("X-GitHub-Event", "push").header("X-GitHub-Delivery", delivery)
                        .header("X-Hub-Signature-256", sign(broken))
                        .contentType(MediaType.APPLICATION_JSON).content(broken))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("BAD_REQUEST"));
        mvc.perform(asUser(get(commitsUrl(repoId)), "ingest-malformed"))
                .andExpect(jsonPath("$.length()").value(0));

        // Gửi lại cùng delivery với payload đúng vẫn được xử lý
        sendWebhook("push", delivery, pushPayload(BILLING.id(), "refs/heads/main", SHA_1))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.status").value("PROCESSED"));
    }

    @Test
    void ping_otherEvents_tags_andRepositoriesOutsideWorkspaces_storeNothing() throws Exception {
        String repoId = connectAndAddRepo("ingest-ignored");

        sendWebhook("ping", newDelivery(), Map.of("zen", "Keep it logically awesome.", "hook_id", 1))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("PONG"));
        sendWebhook("issues", newDelivery(), Map.of("action", "opened", "repository", Map.of("id", BILLING.id())))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.status").value("IGNORED"));
        // BR-25: repo chưa được thêm vào workspace nào
        sendWebhook("push", newDelivery(), pushPayload(777777L, "refs/heads/main", SHA_1))
                .andExpect(jsonPath("$.status").value("IGNORED"));
        // Push tag: không phải commit mới của nhánh nào
        sendWebhook("push", newDelivery(), pushPayload(BILLING.id(), "refs/tags/v1.0", SHA_1))
                .andExpect(jsonPath("$.status").value("PROCESSED"));

        mvc.perform(asUser(get(commitsUrl(repoId)), "ingest-ignored"))
                .andExpect(jsonPath("$.length()").value(0));
    }

    // ------------------------------------------------------------------ Lấy bù khi đồng bộ

    @Test
    void sync_backfillsRecentCommitsAndPullRequests() throws Exception {
        String user = "ingest-sync";
        String repoId = connectAndAddRepo(user);
        mockBillingOnGitHub();
        when(gitHubClient.listCommits(eq(TOKEN), eq("acme"), eq("billing"), eq("main"), anyInt()))
                .thenReturn(List.of(new GitHubCommit(SHA_1, "https://github.com/acme/billing/commit/" + SHA_1,
                        new GitHubCommit.Detail("Initial commit",
                                new GitHubCommit.Person("Hai Dang", "dang@example.com",
                                        Instant.parse("2026-11-05T02:00:00Z")),
                                null, new GitHubCommit.TreeRef(TREE)),
                        new GitHubCommit.Account("d3r-bbb"))));
        Instant updated = Instant.parse("2026-11-05T09:00:00Z");
        when(gitHubClient.listPullRequests(eq(TOKEN), eq("acme"), eq("billing"), anyInt()))
                .thenReturn(List.of(new GitHubPullRequest(3, "Fix totals", null, "open",
                        "https://github.com/acme/billing/pull/3", new GitHubPullRequest.Account("lamhuyy"),
                        new GitHubPullRequest.Ref("fix/totals", SHA_2), new GitHubPullRequest.Ref("main", SHA_1),
                        updated, updated, null, null)));

        mvc.perform(asUser(post(syncUrl(repoId)), user)).andExpect(status().isOk());

        mvc.perform(asUser(get(commitsUrl(repoId)), user))
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].sha").value(SHA_1))
                .andExpect(jsonPath("$[0].branch").value("main"))
                .andExpect(jsonPath("$[0].authorLogin").value("d3r-bbb"))
                .andExpect(jsonPath("$[0].source").value("SYNC"));
        mvc.perform(asUser(get(pullRequestsUrl(repoId)), user))
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].number").value(3))
                .andExpect(jsonPath("$[0].merged").value(false))
                .andExpect(jsonPath("$[0].authorLogin").value("lamhuyy"))
                .andExpect(jsonPath("$[0].source").value("SYNC"));
    }

    @Test
    void sync_stillSucceeds_whenPullRequestsCannotBeListed() throws Exception {
        String user = "ingest-sync-pr-error";
        String repoId = connectAndAddRepo(user);
        mockBillingOnGitHub();
        when(gitHubClient.listPullRequests(eq(TOKEN), eq("acme"), eq("billing"), anyInt()))
                .thenThrow(new GitHubApiException("GitHub API returned HTTP 503.", 503, new HttpHeaders(),
                        "{\"message\":\"unavailable\"}"));

        mvc.perform(asUser(post(syncUrl(repoId)), user))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.repository.fullName").value("acme/billing"));
        mvc.perform(asUser(get(pullRequestsUrl(repoId)), user))
                .andExpect(jsonPath("$.length()").value(0));
    }

    // ------------------------------------------------------------------ Quyền xem, gỡ repo

    @Test
    void otherUserCannotSeeActivity_andRemovingRepositoryRemovesItsActivity() throws Exception {
        String repoId = connectAndAddRepo("ingest-owner");
        sendWebhook("push", newDelivery(), pushPayload(BILLING.id(), "refs/heads/main", SHA_1))
                .andExpect(jsonPath("$.status").value("PROCESSED"));

        mvc.perform(asUser(get(commitsUrl(repoId)), "ingest-stranger")).andExpect(status().isForbidden());
        mvc.perform(asUser(get(pullRequestsUrl(repoId)), "ingest-stranger")).andExpect(status().isForbidden());

        mvc.perform(asUser(delete("/api/repositories/" + repoId), "ingest-owner")).andExpect(status().isNoContent());
        mvc.perform(asUser(get(commitsUrl(repoId)), "ingest-owner")).andExpect(status().isNotFound());
        assertThat(commitRepository.findByRepositoryIdOrderByCommittedAtDesc(UUID.fromString(repoId),
                PageRequest.of(0, 10))).isEmpty();
    }

    // ------------------------------------------------------------------ helpers

    private ResultActions sendWebhook(String event, String delivery, Map<String, Object> payload) throws Exception {
        byte[] body = json.writeValueAsBytes(payload);
        return mvc.perform(post(WEBHOOK)
                .header("X-GitHub-Event", event)
                .header("X-GitHub-Delivery", delivery)
                .header("X-Hub-Signature-256", sign(body))
                .contentType(MediaType.APPLICATION_JSON)
                .content(body));
    }

    private static String sign(byte[] body) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(WEBHOOK_SECRET.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        return "sha256=" + HexFormat.of().formatHex(mac.doFinal(body));
    }

    /** Dạng rút gọn của webhook push: commit thứ i có giờ 10:0i theo múi giờ +07:00. */
    private static Map<String, Object> pushPayload(long githubRepoId, String ref, String... shas) {
        List<Map<String, Object>> commits = new ArrayList<>();
        for (int i = 0; i < shas.length; i++) {
            commits.add(Map.of(
                    "id", shas[i],
                    "message", "Commit " + (i + 1),
                    "timestamp", "2026-11-06T10:0" + i + ":00+07:00",
                    "url", "https://github.com/acme/billing/commit/" + shas[i],
                    "author", Map.of("name", "Hai Dang", "email", "dang@example.com", "username", "d3r-bbb")));
        }
        return Map.of("ref", ref, "deleted", false, "commits", commits,
                "repository", Map.of("id", githubRepoId, "full_name", "acme/billing"));
    }

    private static Map<String, Object> pullRequestPayload(String action, int number, String state,
                                                          String updatedAt, String mergedAt) {
        Map<String, Object> pr = new HashMap<>();  // HashMap vì merged_at có thể null
        pr.put("number", number);
        pr.put("title", "Add invoices");
        pr.put("state", state);
        pr.put("html_url", "https://github.com/acme/billing/pull/" + number);
        pr.put("user", Map.of("login", "d3r-bbb"));
        pr.put("head", Map.of("ref", "feature/invoices", "sha", SHA_2));
        pr.put("base", Map.of("ref", "main", "sha", SHA_1));
        pr.put("created_at", "2026-11-06T03:00:00Z");
        pr.put("updated_at", updatedAt);
        pr.put("closed_at", mergedAt);
        pr.put("merged_at", mergedAt);
        return Map.of("action", action, "number", number, "pull_request", pr,
                "repository", Map.of("id", BILLING.id(), "full_name", "acme/billing"));
    }

    private MockHttpServletRequestBuilder asUser(MockHttpServletRequestBuilder request, String user) {
        return request.header(USER_HEADER, user).header(HttpHeaders.AUTHORIZATION, INTERNAL_AUTH);
    }

    private String connectAndAddRepo(String user) throws Exception {
        GitHubConnection connection = new GitHubConnection();
        connection.setUserId(user);
        connection.setGithubUserId(9100L);
        connection.setGithubLogin("d3r-bbb");
        connection.setAccessToken(TOKEN);
        connection.setAccessTokenExpiresAt(Instant.now().plus(Duration.ofHours(8)));
        connection.setStatus(ConnectionStatus.ACTIVE);
        connectionRepository.save(connection);

        when(gitHubClient.listAccessibleRepositories(TOKEN)).thenReturn(List.of(BILLING));
        String body = mvc.perform(asUser(post("/api/workspaces/ws-" + user + "/repositories"), user)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"githubRepoIds\":[" + BILLING.id() + "]}"))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        return json.readTree(body).get(0).get("id").asText();
    }

    /** Repo acme/billing trên GitHub: nhánh main, một file Java. */
    private void mockBillingOnGitHub() {
        when(gitHubClient.getRepositoryDetails(TOKEN, "acme", "billing")).thenReturn(
                new GitHubRepoDetails(BILLING.id(), "billing", "acme/billing", new GitHubRepoDetails.Owner("acme"),
                        "Billing", false, false, false, "main", BILLING.htmlUrl(), "Java", 8L,
                        Instant.parse("2026-11-05T08:00:00Z")));
        when(gitHubClient.getCommit(TOKEN, "acme", "billing", "main")).thenReturn(new GitHubCommit(SHA_1, null,
                new GitHubCommit.Detail("Initial commit", null, null, new GitHubCommit.TreeRef(TREE)), null));
        when(gitHubClient.getTree(TOKEN, "acme", "billing", TREE)).thenReturn(new GitHubTree(TREE, false, List.of(
                new GitHubTree.Entry("src/Invoice.java", "100644", "blob", APP_SHA, (long) APP_CODE.length()))));
        when(gitHubClient.getBlob(TOKEN, "acme", "billing", APP_SHA)).thenReturn(new GitHubBlob(APP_SHA,
                (long) APP_CODE.length(), "base64",
                Base64.getEncoder().encodeToString(APP_CODE.getBytes(StandardCharsets.UTF_8))));
    }

    private static String newDelivery() {
        return UUID.randomUUID().toString();
    }

    private static String commitsUrl(String repoId) {
        return "/api/repositories/" + repoId + "/commits";
    }

    private static String pullRequestsUrl(String repoId) {
        return "/api/repositories/" + repoId + "/pull-requests";
    }

    private static String syncUrl(String repoId) {
        return "/api/repositories/" + repoId + "/sync";
    }
}
