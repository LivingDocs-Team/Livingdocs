package com.cnpm.backend;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.cnpm.backend.dto.RepositoryDto;
import com.cnpm.backend.exception.GitHubAuthenticationException;
import com.cnpm.backend.service.GitHubService;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@RestClientTest(GitHubService.class)
class GitHubServiceTest {

    @Autowired
    private GitHubService gitHubService;

    @Autowired
    private MockRestServiceServer server;

    @Autowired
    private ObjectMapper objectMapper;

    public record GitHubRepoResponse(String name, String description) {}

    @Test
    void getUserRepositories_WhenGitHubApiReturns401_ShouldThrowCustomLivingDocsException() {
        this.server.expect(requestTo("https://api.github.com/user/repos"))
                .andRespond(withStatus(HttpStatus.UNAUTHORIZED));

        assertThrows(GitHubAuthenticationException.class, () -> {
            gitHubService.getUserRepositories("invalid_access_token");
        });
    }

    @Test
    void getUserRepositories_Success_ShouldReturnMappedData() throws Exception {
        GitHubRepoResponse mockResponse = new GitHubRepoResponse("livingdocs-core", "LivingDocs Core Repository");

        this.server.expect(requestTo("https://api.github.com/user/repos"))
                .andRespond(withSuccess(objectMapper.writeValueAsString(List.of(mockResponse)), MediaType.APPLICATION_JSON));

        List<RepositoryDto> repos = gitHubService.getUserRepositories("valid_token");

        assertEquals(1, repos.size());
        assertEquals("livingdocs-core", repos.get(0).name());
    }
}