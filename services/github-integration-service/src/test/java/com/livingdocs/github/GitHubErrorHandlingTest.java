package com.livingdocs.github;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.client.GitHubRepo;
import com.livingdocs.github.client.GitHubTokenResponse;
import com.livingdocs.github.client.GitHubUser;
import com.livingdocs.github.entity.ConnectionStatus;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.exception.GitHubApiException;
import com.livingdocs.github.repository.GitHubConnectionRepository;
import com.livingdocs.github.security.TokenEncryptor;
import com.livingdocs.github.service.GitHubConnectionService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.client.ResourceAccessException;

import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.Base64;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.hamcrest.Matchers.containsString;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Xử lý lỗi kết nối GitHub (LD-75 – LD-77, danh sách lỗi giai đoạn 1: L05, L06, L08, L10, L11)
 * với database H2 và GitHub giả (mock). Mỗi test dùng user riêng vì database được dùng chung giữa các class test.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(com.livingdocs.github.security.InternalServiceTestMvcConfig.class)
class GitHubErrorHandlingTest {

    private static final String USER_HEADER = "X-User-Id";
    private static final GitHubRepo SHOP =
            new GitHubRepo(4343L, "acme/shop", false, "main", "https://github.com/acme/shop");

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired JdbcTemplate jdbc;
    @Autowired GitHubConnectionRepository connectionRepository;
    @Autowired GitHubConnectionService connectionService;

    @MockitoBean GitHubClient gitHubClient;

    // ------------------------------------------------------------------ L05: lỗi khi làm mới token

    @Test
    void refreshNetworkError_keepsConnectionActive() throws Exception {
        String user = "err-refresh-network";
        saveConnection(user, "ghu_old", "ghr_old", Instant.now().plusSeconds(60));
        when(gitHubClient.refreshToken("ghr_old")).thenThrow(new GitHubApiException(
                "Unable to contact GitHub API.", new ResourceAccessException("Connection refused")));

        mvc.perform(get("/api/github/repos/available").header(USER_HEADER, user))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.code").value("GITHUB_API_ERROR"));

        assertThat(statusOf(user)).isEqualTo(ConnectionStatus.ACTIVE);
        verify(gitHubClient, never()).listAccessibleRepositories(anyString());
    }

    @Test
    void refreshServerError_keepsConnectionActive() {
        String user = "err-refresh-5xx";
        saveConnection(user, "ghu_old", "ghr_old", Instant.now().plusSeconds(60));
        when(gitHubClient.refreshToken("ghr_old")).thenThrow(
                new GitHubApiException("GitHub API returned HTTP 503.", 503, new HttpHeaders(), ""));

        assertThatThrownBy(() -> connectionService.getActiveConnection(user))
                .isInstanceOf(GitHubApiException.class);

        assertThat(statusOf(user)).isEqualTo(ConnectionStatus.ACTIVE);
        assertThat(connectionRepository.findByUserId(user).orElseThrow().getRefreshToken()).isEqualTo("ghr_old");
    }

    @Test
    void rejectedRefreshToken_marksConnectionInvalid() throws Exception {
        String user = "err-refresh-rejected";
        saveConnection(user, "ghu_old", "ghr_old", Instant.now().plusSeconds(60));
        when(gitHubClient.refreshToken("ghr_old")).thenThrow(
                new GitHubApiException("GitHub OAuth token exchange was rejected.", true));

        mvc.perform(get("/api/github/repos/available").header(USER_HEADER, user))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("GITHUB_REAUTH_REQUIRED"));

        assertThat(statusOf(user)).isEqualTo(ConnectionStatus.INVALID);
    }

    // ------------------------------------------------------------------ L06: làm mới token đồng thời

    @Test
    void concurrentRequests_useRefreshTokenOnlyOnce() throws Exception {
        String user = "err-refresh-race";
        saveConnection(user, "ghu_old", "ghr_old", Instant.now().plusSeconds(60));
        CountDownLatch refreshStarted = new CountDownLatch(1);
        CountDownLatch releaseRefresh = new CountDownLatch(1);
        when(gitHubClient.refreshToken("ghr_old")).thenAnswer(call -> {
            refreshStarted.countDown();
            if (!releaseRefresh.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("test timed out");
            }
            return new GitHubTokenResponse("ghu_new", 28800L, "ghr_new", 15897600L, "bearer", "", null, null);
        });

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<GitHubConnection> first = pool.submit(() -> connectionService.getActiveConnection(user));
            assertThat(refreshStarted.await(10, TimeUnit.SECONDS)).isTrue();
            // Request thứ hai đọc kết nối khi token cũ chưa được thay, rồi phải chờ request thứ nhất làm mới xong
            Future<GitHubConnection> second = pool.submit(() -> connectionService.getActiveConnection(user));
            Thread.sleep(300);
            releaseRefresh.countDown();

            assertThat(first.get(10, TimeUnit.SECONDS).getAccessToken()).isEqualTo("ghu_new");
            assertThat(second.get(10, TimeUnit.SECONDS).getAccessToken()).isEqualTo("ghu_new");
        } finally {
            pool.shutdownNow();
        }

        verify(gitHubClient, times(1)).refreshToken("ghr_old");
        GitHubConnection stored = connectionRepository.findByUserId(user).orElseThrow();
        assertThat(stored.getStatus()).isEqualTo(ConnectionStatus.ACTIVE);
        assertThat(stored.getAccessToken()).isEqualTo("ghu_new");
        assertThat(stored.getRefreshToken()).isEqualTo("ghr_new");
    }

    // ------------------------------------------------------------------ L08: token mã hoá bằng khoá khác

    @Test
    void tokenEncryptedWithAnotherKey_reportsInvalid_andUserCanDisconnect() throws Exception {
        String user = "err-old-key";
        saveConnection(user, "ghu_live", "ghr_live", Instant.now().plus(Duration.ofHours(8)));
        byte[] otherKey = new byte[32];
        Arrays.fill(otherKey, (byte) 7);
        TokenEncryptor oldEncryptor = new TokenEncryptor(Base64.getEncoder().encodeToString(otherKey));
        jdbc.update("update github_connections set access_token = ?, refresh_token = ? where user_id = ?",
                oldEncryptor.encrypt("ghu_live"), oldEncryptor.encrypt("ghr_live"), user);

        mvc.perform(get("/api/github/connection").header(USER_HEADER, user))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.connected").value(false))
                .andExpect(jsonPath("$.status").value("INVALID"));
        mvc.perform(get("/api/github/repos/available").header(USER_HEADER, user))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("GITHUB_REAUTH_REQUIRED"));
        assertThat(statusOf(user)).isEqualTo(ConnectionStatus.INVALID);

        mvc.perform(delete("/api/github/connection").header(USER_HEADER, user))
                .andExpect(status().isNoContent());
        assertThat(statusOf(user)).isEqualTo(ConnectionStatus.REVOKED);
        verify(gitHubClient, never()).listAccessibleRepositories(anyString());
        verify(gitHubClient, never()).revokeGrant(anyString());
    }

    // ------------------------------------------------------------------ L10: thêm nhiều repo

    @Test
    void addRepositories_withOneNotAllowedId_savesNothing() throws Exception {
        String user = "err-add-partial";
        saveConnection(user, "ghu_add", "ghr_add", Instant.now().plus(Duration.ofHours(8)));
        when(gitHubClient.listAccessibleRepositories("ghu_add")).thenReturn(List.of(SHOP));

        mvc.perform(post("/api/workspaces/ws-" + user + "/repositories").header(USER_HEADER, user)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"githubRepoIds\":[" + SHOP.id() + ",999]}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value(containsString("999")));

        mvc.perform(get("/api/workspaces/ws-" + user + "/repositories").header(USER_HEADER, user))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(0));
    }

    // ------------------------------------------------------------------ L11: kết nối lại

    @Test
    void reconnectWithSameAccount_makesRepositoriesUsableAgain() throws Exception {
        String user = "err-reconnect-same";
        connect(user, "code-same-1", "ghu_same_1", 6001L, "dang-a");
        String repoId = addShop(user, "ghu_same_1");

        mvc.perform(delete("/api/github/connection").header(USER_HEADER, user))
                .andExpect(status().isNoContent());
        assertThat(repositoryStatus(user, repoId)).isEqualTo("DISCONNECTED");

        connect(user, "code-same-2", "ghu_same_2", 6001L, "dang-a");
        assertThat(repositoryStatus(user, repoId)).isEqualTo("CONNECTED");
    }

    @Test
    void reconnectWithAnotherAccount_marksOldRepositoriesDisconnected() throws Exception {
        String user = "err-reconnect-other";
        connect(user, "code-other-1", "ghu_other_1", 6002L, "dang-a");
        String repoId = addShop(user, "ghu_other_1");

        connect(user, "code-other-2", "ghu_other_2", 7002L, "someone-else");

        assertThat(repositoryStatus(user, repoId)).isEqualTo("DISCONNECTED");
        mvc.perform(get("/api/github/connection").header(USER_HEADER, user))
                .andExpect(jsonPath("$.connected").value(true))
                .andExpect(jsonPath("$.githubLogin").value("someone-else"));
    }

    // ------------------------------------------------------------------ handler chung cho lỗi không lường trước

    @Test
    void unknownPath_staysNotFound() throws Exception {
        mvc.perform(get("/api/khong-ton-tai").header(USER_HEADER, "err-unknown-path"))
                .andExpect(status().isNotFound());
    }

    // ------------------------------------------------------------------ dữ liệu giả

    /** Kết nối ACTIVE lưu thẳng vào database (token được mã hoá như khi chạy thật). */
    private void saveConnection(String user, String accessToken, String refreshToken, Instant expiresAt) {
        GitHubConnection connection = new GitHubConnection();
        connection.setUserId(user);
        connection.setGithubUserId(5555L);
        connection.setGithubLogin("d3r-bbb");
        connection.setAccessToken(accessToken);
        connection.setRefreshToken(refreshToken);
        connection.setAccessTokenExpiresAt(expiresAt);
        connection.setStatus(ConnectionStatus.ACTIVE);
        connectionRepository.save(connection);
    }

    /** Đi qua đúng luồng OAuth: lấy state, GitHub gọi callback với code. */
    private void connect(String user, String code, String accessToken, long githubUserId, String login)
            throws Exception {
        String body = mvc.perform(get("/api/github/authorize-url").header(USER_HEADER, user))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        String state = json.readTree(body).get("state").asText();

        when(gitHubClient.exchangeCode(code)).thenReturn(new GitHubTokenResponse(
                accessToken, 28800L, "ghr_" + code, 15897600L, "bearer", "", null, null));
        when(gitHubClient.getAuthenticatedUser(accessToken)).thenReturn(new GitHubUser(githubUserId, login));

        mvc.perform(get("/api/github/callback").param("code", code).param("state", state))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.githubLogin").value(login));
    }

    /** Thêm repo acme/shop vào workspace riêng của user; trả về id repo. */
    private String addShop(String user, String accessToken) throws Exception {
        when(gitHubClient.listAccessibleRepositories(accessToken)).thenReturn(List.of(SHOP));
        String body = mvc.perform(post("/api/workspaces/ws-" + user + "/repositories").header(USER_HEADER, user)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"githubRepoIds\":[" + SHOP.id() + "]}"))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        return json.readTree(body).get(0).get("id").asText();
    }

    private String repositoryStatus(String user, String repoId) throws Exception {
        String body = mvc.perform(get("/api/repositories/" + repoId).header(USER_HEADER, user))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        JsonNode node = json.readTree(body);
        return node.get("status").asText();
    }

    private ConnectionStatus statusOf(String user) {
        return connectionRepository.findByUserId(user).orElseThrow().getStatus();
    }
}



