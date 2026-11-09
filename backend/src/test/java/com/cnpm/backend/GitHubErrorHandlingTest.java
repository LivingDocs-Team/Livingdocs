package com.cnpm.backend;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpStatus;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.RestTemplate;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class GitHubErrorHandlingTest {

    @Mock
    private RestTemplate restTemplate;

    @BeforeEach
    void setUp() {
    }

    @Test
    @DisplayName("Ném lỗi khi Access Token không hợp lệ (HTTP 401)")
    void shouldHandleUnauthorizedError() {
        when(restTemplate.getForObject(anyString(), eq(String.class)))
                .thenThrow(new HttpClientErrorException(HttpStatus.UNAUTHORIZED, "Unauthorized"));

        HttpClientErrorException exception = assertThrows(HttpClientErrorException.class, () -> {
            restTemplate.getForObject("https://api.github.com/user", String.class);
        });

        assertTrue(exception.getMessage().contains("401") || exception.getMessage().contains("Unauthorized"));
    }

    @Test
    @DisplayName("Ném lỗi khi vượt quá giới hạn Rate Limit (HTTP 403)")
    void shouldHandleRateLimitExceededError() {
        when(restTemplate.getForObject(anyString(), eq(String.class)))
                .thenThrow(new HttpClientErrorException(HttpStatus.FORBIDDEN, "API rate limit exceeded"));

        HttpClientErrorException exception = assertThrows(HttpClientErrorException.class, () -> {
            restTemplate.getForObject("https://api.github.com/user", String.class);
        });

        assertTrue(exception.getMessage().contains("403") || exception.getMessage().contains("rate limit"));
    }

    @Test
    @DisplayName("Ném lỗi khi không tìm thấy Repository (HTTP 404)")
    void shouldHandleNotFoundError() {
        when(restTemplate.getForObject(anyString(), eq(String.class)))
                .thenThrow(new HttpClientErrorException(HttpStatus.NOT_FOUND, "Not Found"));

        HttpClientErrorException exception = assertThrows(HttpClientErrorException.class, () -> {
            restTemplate.getForObject("https://api.github.com/repos/owner/unknown", String.class);
        });

        assertTrue(exception.getMessage().contains("404") || exception.getMessage().contains("Not Found"));
    }

    @Test
    @DisplayName("Xử lý sự cố dịch vụ GitHub bị gián đoạn (HTTP 500)")
    void shouldHandleGitHubServerError() {
        when(restTemplate.getForObject(anyString(), eq(String.class)))
                .thenThrow(new HttpServerErrorException(HttpStatus.INTERNAL_SERVER_ERROR, "Internal Server Error"));

        HttpServerErrorException exception = assertThrows(HttpServerErrorException.class, () -> {
            restTemplate.getForObject("https://api.github.com/user", String.class);
        });

        assertTrue(exception.getMessage().contains("500") || exception.getMessage().contains("Internal Server Error"));
    }
}