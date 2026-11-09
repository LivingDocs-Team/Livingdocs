package com.livingdocs.service;

import com.livingdocs.exception.GithubAPIException;
import com.livingdocs.model.GithubRepoDto;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

@RestClientTest(GithubIntegrationService.class) // Test chính xác Service thật của LivingDocs
class GithubIntegrationServiceTest {

    @Autowired
    private GithubIntegrationService githubIntegrationService;

    @Autowired
    private MockRestServiceServer mockServer;

    @Test
    @DisplayName("Phải quăng GithubAPIException khi GitHub Rest API trả về lỗi HTTP 401 Unauthorized")
    void shouldThrowGithubAPIException_WhenGithubApiReturns401() {
        // Arrange: Giả lập HTTP Response từ GitHub Server thực tế
        mockServer.expect(requestTo("https://api.github.com/user/repos"))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header("Authorization", "Bearer invalid_token"))
                .andRespond(withStatus(HttpStatus.UNAUTHORIZED)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body("{\"message\": \"Bad credentials\"}"));

        // Act & Assert: Gọi Service THỰC TẾ của LivingDocs và verify Custom Exception
        GithubAPIException exception = assertThrows(
                GithubAPIException.class,
                () -> githubIntegrationService.getUserRepositories("invalid_token")
        );

        assertEquals(HttpStatus.UNAUTHORIZED, exception.getStatus());
        assertEquals("Bad credentials", exception.getMessage());
        
        // Đảm bảo request thực sự đã gửi ra ngoài theo đúng spec
        mockServer.verify();
    }
}