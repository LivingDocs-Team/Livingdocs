package com.livingdocs.github;

import com.livingdocs.github.dto.ErrorResponse;
import com.livingdocs.github.exception.GitHubApiException;
import com.livingdocs.github.exception.GlobalExceptionHandler;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

class GlobalExceptionHandlerSecurityTest {

    @Test
    void doesNotReturnRawUpstreamErrorBodyAndKeepsSafeStatusDiagnostic() {
        String upstreamMarker = "sensitive-upstream-marker";
        GitHubApiException failure = new GitHubApiException(
                "untrusted upstream message " + upstreamMarker,
                403,
                new HttpHeaders(),
                "{\"message\":\"" + upstreamMarker + "\"}");

        ResponseEntity<ErrorResponse> response = new GlobalExceptionHandler().handleGitHub(failure);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_GATEWAY);
        assertThat(response.getBody().message()).doesNotContain(upstreamMarker);
        assertThat(response.getBody().message()).contains("HTTP 403");
    }
}
