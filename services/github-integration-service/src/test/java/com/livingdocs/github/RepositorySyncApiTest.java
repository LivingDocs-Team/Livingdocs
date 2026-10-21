package com.livingdocs.github;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.client.GitHubBlob;
import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.client.GitHubCommit;
import com.livingdocs.github.client.GitHubRepo;
import com.livingdocs.github.client.GitHubRepoDetails;
import com.livingdocs.github.client.GitHubTree;
import com.livingdocs.github.entity.ConnectionStatus;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.entity.RepositoryStatus;
import com.livingdocs.github.exception.GitHubApiException;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.repository.GitHubConnectionRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * API đồng bộ repository (LD-63) với database H2 và GitHub giả (mock).
 * Mỗi test dùng user và workspace riêng vì database được dùng chung giữa các class test.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(com.livingdocs.github.security.InternalServiceTestMvcConfig.class)
class RepositorySyncApiTest {

    private static final String USER_HEADER = "X-User-Id";
    private static final String TOKEN = "ghu_sync_token";
    private static final String HEAD = "a1".repeat(20);
    private static final String TREE = "b2".repeat(20);
    private static final String APP_SHA = "c3".repeat(20);
    private static final String README_SHA = "d4".repeat(20);
    private static final String APP_CODE = "public class App {\n}\n";
    private static final GitHubRepo SHOP =
            new GitHubRepo(4242L, "acme/shop", false, "main", "https://github.com/acme/shop");

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired GitHubConnectionRepository connectionRepository;
    @Autowired ConnectedRepositoryRepository repositoryRepository;

    @MockitoBean GitHubClient gitHubClient;

    @Test
    void sync_returnsResultWithoutContent_andUpdatesRepository() throws Exception {
        String user = "sync-ok";
        String repoId = connectAndAddRepo(user);
        assertThat(lastSyncedAt(repoId)).isNull();
        mockShopOnGitHub("develop");
        // Trong lúc đang gọi GitHub, repo phải ở trạng thái SYNCING
        AtomicReference<RepositoryStatus> statusDuringSync = new AtomicReference<>();
        when(gitHubClient.getRepositoryDetails(TOKEN, "acme", "shop")).thenAnswer(call -> {
            statusDuringSync.set(repositoryRepository.findById(UUID.fromString(repoId)).orElseThrow().getStatus());
            return shopDetails("develop");
        });

        mvc.perform(post(syncUrl(repoId)).header(USER_HEADER, user))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.repository.fullName").value("acme/shop"))
                .andExpect(jsonPath("$.branch").value("develop"))
                .andExpect(jsonPath("$.headCommit.sha").value(HEAD))
                .andExpect(jsonPath("$.files.length()").value(1))
                .andExpect(jsonPath("$.files[0].path").value("src/App.java"))
                .andExpect(jsonPath("$.files[0].language").value("java"))
                .andExpect(jsonPath("$.files[0].analyzable").value(true))
                .andExpect(jsonPath("$.files[0].content").doesNotExist())
                .andExpect(jsonPath("$.stats.totalFilesInRepo").value(2))
                .andExpect(jsonPath("$.stats.filesWithContent").value(1))
                .andExpect(jsonPath("$.syncedAt").exists());

        assertThat(statusDuringSync.get()).isEqualTo(RepositoryStatus.SYNCING);
        mvc.perform(get("/api/repositories/" + repoId).header(USER_HEADER, "sync-ok"))
                .andExpect(jsonPath("$.status").value("CONNECTED"))
                .andExpect(jsonPath("$.defaultBranch").value("develop"));
        assertThat(lastSyncedAt(repoId)).isNotNull(); // LD-66
    }

    @Test
    void latestAndAnalysisInput_returnLastSyncResult() throws Exception {
        String user = "sync-latest";
        String repoId = connectAndAddRepo(user);

        mvc.perform(get(syncUrl(repoId) + "/latest").header(USER_HEADER, user))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("NOT_FOUND"));

        mockShopOnGitHub("main");
        mvc.perform(post(syncUrl(repoId)).header(USER_HEADER, user)).andExpect(status().isOk());

        mvc.perform(get(syncUrl(repoId) + "/latest").header(USER_HEADER, user))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.headCommit.sha").value(HEAD))
                .andExpect(jsonPath("$.files[0].content").doesNotExist());
        mvc.perform(get(syncUrl(repoId) + "/latest/analysis-input").header(USER_HEADER, user))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.scope").value("repository"))
                .andExpect(jsonPath("$.target").value("acme/shop"))
                .andExpect(jsonPath("$.files.length()").value(1))
                .andExpect(jsonPath("$.files[0].path").value("src/App.java"))
                .andExpect(jsonPath("$.files[0].language").value("java"))
                .andExpect(jsonPath("$.files[0].content").value(APP_CODE));
    }

    @Test
    void otherUser_isForbidden_unknownRepository_isNotFound() throws Exception {
        String repoId = connectAndAddRepo("sync-owner");

        mvc.perform(post(syncUrl(repoId)).header(USER_HEADER, "sync-nguoi-khac"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("FORBIDDEN"));
        mvc.perform(get(syncUrl(repoId) + "/latest/analysis-input").header(USER_HEADER, "sync-nguoi-khac"))
                .andExpect(status().isForbidden());
        mvc.perform(post(syncUrl(UUID.randomUUID().toString())).header(USER_HEADER, "sync-owner"))
                .andExpect(status().isNotFound());
        mvc.perform(post(syncUrl(repoId))) // thiếu header X-User-Id
                .andExpect(status().isBadRequest());

        verify(gitHubClient, never()).getRepositoryDetails(anyString(), anyString(), anyString());
    }

    @Test
    void invalidInput_isBadRequest_andDoesNotCallGitHub() throws Exception {
        String user = "sync-input";
        String repoId = connectAndAddRepo(user);

        mvc.perform(post(syncUrl(repoId)).header(USER_HEADER, user)
                        .contentType(MediaType.APPLICATION_JSON).content("{\"maxFiles\": 0}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));
        mvc.perform(post(syncUrl(repoId)).header(USER_HEADER, user)
                        .contentType(MediaType.APPLICATION_JSON).content("{khong phai json"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("BAD_REQUEST"));
        mvc.perform(post("/api/repositories/khong-phai-uuid/sync").header(USER_HEADER, user))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("BAD_REQUEST"));

        verify(gitHubClient, never()).getRepositoryDetails(anyString(), anyString(), anyString());
        mvc.perform(get("/api/repositories/" + repoId).header(USER_HEADER, "sync-input")).andExpect(jsonPath("$.status").value("CONNECTED"));
    }

    @Test
    void branchNotFound_is404_andKeepsStatus() throws Exception {
        String user = "sync-branch";
        String repoId = connectAndAddRepo(user);
        mockShopOnGitHub("main");
        when(gitHubClient.getCommit(TOKEN, "acme", "shop", "khong-co")).thenThrow(gitHubError(404, null));

        mvc.perform(post(syncUrl(repoId)).header(USER_HEADER, user)
                        .contentType(MediaType.APPLICATION_JSON).content("{\"branch\": \"khong-co\"}"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("BRANCH_NOT_FOUND"));

        mvc.perform(get("/api/repositories/" + repoId).header(USER_HEADER, "sync-branch")).andExpect(jsonPath("$.status").value("CONNECTED"));
    }

    @Test
    void repositoryGoneOnGitHub_marksRepositoryError() throws Exception {
        String user = "sync-gone";
        String repoId = connectAndAddRepo(user);
        when(gitHubClient.getRepositoryDetails(TOKEN, "acme", "shop")).thenThrow(gitHubError(404, null));

        mvc.perform(post(syncUrl(repoId)).header(USER_HEADER, user))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("REPOSITORY_NOT_FOUND"));

        mvc.perform(get("/api/repositories/" + repoId).header(USER_HEADER, "sync-gone")).andExpect(jsonPath("$.status").value("ERROR"));
    }

    @Test
    void revokedToken_marksConnectionInvalid() throws Exception {
        String user = "sync-token";
        String repoId = connectAndAddRepo(user);
        when(gitHubClient.getRepositoryDetails(TOKEN, "acme", "shop")).thenThrow(gitHubError(401, null));

        mvc.perform(post(syncUrl(repoId)).header(USER_HEADER, user))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("TOKEN_INVALID"));

        assertThat(connectionRepository.findByUserId(user).orElseThrow().getStatus())
                .isEqualTo(ConnectionStatus.INVALID);
        mvc.perform(get("/api/repositories/" + repoId).header(USER_HEADER, "sync-token")).andExpect(jsonPath("$.status").value("CONNECTED"));
    }

    @Test
    void rateLimited_is429WithRetryAfter_andKeepsStatus() throws Exception {
        String user = "sync-limit";
        String repoId = connectAndAddRepo(user);
        HttpHeaders headers = new HttpHeaders();
        headers.add("x-ratelimit-remaining", "0");
        headers.add("x-ratelimit-reset", String.valueOf(Instant.now().plusSeconds(120).getEpochSecond()));
        when(gitHubClient.getRepositoryDetails(TOKEN, "acme", "shop")).thenThrow(gitHubError(403, headers));

        mvc.perform(post(syncUrl(repoId)).header(USER_HEADER, user))
                .andExpect(status().isTooManyRequests())
                .andExpect(header().exists(HttpHeaders.RETRY_AFTER))
                .andExpect(jsonPath("$.code").value("RATE_LIMITED"));

        mvc.perform(get("/api/repositories/" + repoId).header(USER_HEADER, "sync-limit")).andExpect(jsonPath("$.status").value("CONNECTED"));
    }

    // ------------------------------------------------------------------ dữ liệu giả

    private static String syncUrl(String repoId) {
        return "/api/repositories/" + repoId + "/sync";
    }

    /** Tạo kết nối GitHub cho user rồi thêm repo acme/shop vào workspace riêng của user đó; trả về id repo. */
    private String connectAndAddRepo(String user) throws Exception {
        GitHubConnection connection = new GitHubConnection();
        connection.setUserId(user);
        connection.setGithubUserId(9000L);
        connection.setGithubLogin("d3r-bbb");
        connection.setAccessToken(TOKEN);
        connection.setAccessTokenExpiresAt(Instant.now().plus(Duration.ofHours(8)));
        connection.setStatus(ConnectionStatus.ACTIVE);
        connectionRepository.save(connection);

        when(gitHubClient.listAccessibleRepositories(TOKEN)).thenReturn(List.of(SHOP));
        String body = mvc.perform(post("/api/workspaces/ws-" + user + "/repositories").header(USER_HEADER, user)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"githubRepoIds\":[" + SHOP.id() + "]}"))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        return json.readTree(body).get(0).get("id").asText();
    }

    private Instant lastSyncedAt(String repoId) throws Exception {
        String body = mvc.perform(get("/api/repositories/" + repoId).header(USER_HEADER, "sync-ok"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        var value = json.readTree(body).get("lastSyncedAt");
        return value == null || value.isNull() ? null : Instant.parse(value.asText());
    }

    /** Repo acme/shop trên GitHub: 1 file Java (lấy nội dung) và 1 README (bỏ qua vì không phải code). */
    private void mockShopOnGitHub(String defaultBranch) {
        when(gitHubClient.getRepositoryDetails(TOKEN, "acme", "shop")).thenReturn(shopDetails(defaultBranch));
        when(gitHubClient.getCommit(TOKEN, "acme", "shop", defaultBranch)).thenReturn(new GitHubCommit(HEAD, null,
                new GitHubCommit.Detail("Initial commit", null, null, new GitHubCommit.TreeRef(TREE)), null));
        when(gitHubClient.getTree(TOKEN, "acme", "shop", TREE)).thenReturn(new GitHubTree(TREE, false, List.of(
                new GitHubTree.Entry("src/App.java", "100644", "blob", APP_SHA, (long) APP_CODE.length()),
                new GitHubTree.Entry("README.md", "100644", "blob", README_SHA, 6L))));
        when(gitHubClient.getBlob(TOKEN, "acme", "shop", APP_SHA)).thenReturn(new GitHubBlob(APP_SHA,
                (long) APP_CODE.length(), "base64",
                Base64.getEncoder().encodeToString(APP_CODE.getBytes(StandardCharsets.UTF_8))));
    }

    private static GitHubRepoDetails shopDetails(String defaultBranch) {
        return new GitHubRepoDetails(SHOP.id(), "shop", "acme/shop", new GitHubRepoDetails.Owner("acme"),
                "Demo shop", false, false, false, defaultBranch, SHOP.htmlUrl(), "Java", 12L,
                Instant.parse("2026-10-13T08:00:00Z"));
    }

    private static GitHubApiException gitHubError(int status, HttpHeaders headers) {
        return new GitHubApiException("GitHub API trả lỗi " + status, status, headers, "{\"message\":\"error\"}");
    }
}
