package com.cnpm.backend;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import com.cnpm.backend.controller.GitHubOAuthController;
import com.cnpm.backend.repository.UserRepository;
import com.cnpm.backend.service.GitHubOAuthService;

import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(GitHubOAuthController.class)
@AutoConfigureMockMvc(addFilters = false)
class GitHubOAuthControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private GitHubOAuthService gitHubOAuthService;

    @MockitoBean
    private UserRepository userRepository;

    public record AuthTokenResponse(String accessToken) {}

    public static class InvalidOAuthCodeException extends RuntimeException {
        public InvalidOAuthCodeException(String message) {
            super(message);
        }
    }

    @Test
    void handleGitHubCallback_WithValidCode_ShouldReturnAuthToken() throws Exception {
        String authCode = "valid_github_code";
        AuthTokenResponse expectedResponse = new AuthTokenResponse("jwt_access_token_123");

        when(gitHubOAuthService.processOAuthCallback(authCode)).thenReturn(expectedResponse);

        mockMvc.perform(get("/api/v1/auth/github/callback")
                        .param("code", authCode)
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accessToken").value("jwt_access_token_123"));

        verify(gitHubOAuthService, times(1)).processOAuthCallback(authCode);
    }

    @Test
    void handleGitHubCallback_WhenServiceThrowsError_ShouldReturn400BadRequest() throws Exception {
        String invalidCode = "invalid_code";

        when(gitHubOAuthService.processOAuthCallback(invalidCode))
                .thenThrow(new InvalidOAuthCodeException("Code không hợp lệ hoặc đã hết hạn"));

        mockMvc.perform(get("/api/v1/auth/github/callback")
                        .param("code", invalidCode))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value("Code không hợp lệ hoặc đã hết hạn"));
    }
}