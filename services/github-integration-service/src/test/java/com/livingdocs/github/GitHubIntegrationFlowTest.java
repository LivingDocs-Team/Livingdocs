package com.livingdocs.github;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.client.GitHubRepo;
import com.livingdocs.github.client.GitHubTokenResponse;
import com.livingdocs.github.client.GitHubUser;
import com.livingdocs.github.exception.GitHubApiException;
import com.livingdocs.github.repository.GitHubConnectionRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Chạy toàn bộ luồng với database H2 và GitHub giả (mock):
 * kết nối -> xem trạng thái -> liệt kê repo -> thêm repo -> đồng bộ -> gỡ repo -> ngắt kết nối.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class GitHubIntegrationFlowTest {

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired GitHubConnectionRepository connectionRepository;
    @Autowired JdbcTemplate jdbc;

    @MockitoBean GitHubClient gitHubClient;

    private static final GitHubRepo REPO_A =
            new GitHubRepo(101L, "LivingDocs-Team/livingdocs", false, "main", "https://github.com/LivingDocs-Team/livingdocs");
    private static final GitHubRepo REPO_B =
            new GitHubRepo(202L, "d3r-bbb/demo", true, "master", "https://github.com/d3r-bbb/demo");

    @Test
    void fullFlow() throws Exception {
        String user = "user-flow";
        connect(user, "code-1");

        // Trạng thái kết nối - không lộ token
        mvc.perform(get("/api/github/connection").header("X-User-Id", user))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.connected").value(true))
                .andExpect(jsonPath("$.githubLogin").value("d3r-bbb"))
                .andExpect(jsonPath("$.accessToken").doesNotExist());

        // Token lưu trong DB đã được mã hoá
        String rawToken = jdbc.queryForObject(
                "select access_token from github_connections where user_id = ?", String.class, user);
        assertThat(rawToken).isNotEqualTo("ghu_token_1");

        // Liệt kê repo có thể thêm
        when(gitHubClient.listAccessibleRepositories("ghu_token_1")).thenReturn(List.of(REPO_A, REPO_B));
        mvc.perform(get("/api/github/repos/available").header("X-User-Id", user))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2));

        // Thêm repo vào workspace (thêm trùng sẽ bị bỏ qua)
        mvc.perform(post("/api/workspaces/ws-1/repositories").header("X-User-Id", user)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"githubRepoIds\":[101,101]}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].status").value("CONNECTED"))
                .andExpect(jsonPath("$[0].defaultBranch").value("main"));

        // Repo không được cấp quyền thì bị từ chối
        mvc.perform(post("/api/workspaces/ws-1/repositories").header("X-User-Id", user)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"githubRepoIds\":[999]}"))
                .andExpect(status().isBadRequest());

        // Danh sách repo của workspace
        String listBody = mvc.perform(get("/api/workspaces/ws-1/repositories"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andReturn().getResponse().getContentAsString();
        String repoId = json.readTree(listBody).get(0).get("id").asText();

        // Đồng bộ lại: nhánh mặc định đổi trên GitHub
        when(gitHubClient.getRepository("ghu_token_1", "LivingDocs-Team/livingdocs")).thenReturn(
                new GitHubRepo(101L, "LivingDocs-Team/livingdocs", false, "develop", REPO_A.htmlUrl()));
        mvc.perform(post("/api/repositories/" + repoId + "/sync").header("X-User-Id", user))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.defaultBranch").value("develop"));

        // Người khác không được gỡ repo của mình
        mvc.perform(delete("/api/repositories/" + repoId).header("X-User-Id", "nguoi-khac"))
                .andExpect(status().isForbidden());

        // Gỡ repo
        mvc.perform(delete("/api/repositories/" + repoId).header("X-User-Id", user))
                .andExpect(status().isNoContent());
        mvc.perform(get("/api/repositories/" + repoId)).andExpect(status().isNotFound());

        // Ngắt kết nối GitHub
        mvc.perform(delete("/api/github/connection").header("X-User-Id", user))
                .andExpect(status().isNoContent());
        mvc.perform(get("/api/github/connection").header("X-User-Id", user))
                .andExpect(jsonPath("$.connected").value(false))
                .andExpect(jsonPath("$.status").value("REVOKED"));
        mvc.perform(get("/api/github/repos/available").header("X-User-Id", user))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("GITHUB_NOT_CONNECTED"));
    }

    @Test
    void callbackWithInvalidState_isRejected() throws Exception {
        mvc.perform(get("/api/github/callback").param("code", "abc").param("state", "gia-mao"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void missingUserHeader_isBadRequest() throws Exception {
        mvc.perform(get("/api/github/connection")).andExpect(status().isBadRequest());
    }

    @Test
    void revokedTokenOnGitHub_marksConnectionInvalid() throws Exception {
        String user = "user-invalid";
        connect(user, "code-2");
        when(gitHubClient.listAccessibleRepositories(anyString()))
                .thenThrow(new GitHubApiException("401 Bad credentials", true));

        mvc.perform(get("/api/github/repos/available").header("X-User-Id", user))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("GITHUB_REAUTH_REQUIRED"));

        assertThat(connectionRepository.findByUserId(user).orElseThrow().getStatus().name())
                .isEqualTo("INVALID");
    }

    private void connect(String user, String code) throws Exception {
        String body = mvc.perform(get("/api/github/authorize-url").header("X-User-Id", user))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.authorizeUrl").value(org.hamcrest.Matchers.containsString("client_id=test-client-id")))
                .andExpect(jsonPath("$.installUrl").value(org.hamcrest.Matchers.containsString("/apps/livingdocs-test/installations/new")))
                .andReturn().getResponse().getContentAsString();
        JsonNode node = json.readTree(body);
        String state = node.get("state").asText();

        when(gitHubClient.exchangeCode(code)).thenReturn(
                new GitHubTokenResponse("ghu_token_1", 28800L, "ghr_refresh_1", 15897600L, "bearer", "", null, null));
        when(gitHubClient.getAuthenticatedUser("ghu_token_1")).thenReturn(new GitHubUser(5555L, "d3r-bbb"));

        mvc.perform(get("/api/github/callback").param("code", code).param("state", state))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.githubLogin").value("d3r-bbb"));
    }
}
