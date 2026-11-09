package com.livingdocs.controller;

import com.livingdocs.dto.GithubAuthResponse;
import com.livingdocs.service.GithubOAuthService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(GithubOAuthController.class) // Target trực tiếp Controller thật
class GithubOAuthControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private GithubOAuthService githubOAuthService; // Mock tầng Business Logic phụ thuộc

    @Test
    @DisplayName("OAuth Callback: Trả về HTTP 200 và JWT Token khi Code & State hợp lệ")
    void shouldReturnTokens_WhenOAuthCallbackIsSuccessful() throws Exception {
        // Arrange
        String code = "valid_github_code";
        String state = "valid_state_secret";
        GithubAuthResponse authResponse = new GithubAuthResponse("jwt_access_token_example", "livingdocs_user");

        given(githubOAuthService.processOAuthCallback(eq(code), eq(state)))
                .willReturn(authResponse);

        // Act & Assert: Gọi HTTP GET vào đường dẫn endpoint THỰC TẾ của LivingDocs
        mockMvc.perform(get("/api/v1/auth/github/callback")
                        .param("code", code)
                        .param("state", state)
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accessToken").value("jwt_access_token_example"))
                .andExpect(jsonPath("$.username").value("livingdocs_user"));
    }
}