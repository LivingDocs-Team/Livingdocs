package com.livingdocs.github;

import com.livingdocs.github.dto.ErrorResponse;
import com.livingdocs.github.exception.GitHubApiException;
import com.livingdocs.github.exception.GlobalExceptionHandler;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.server.ResponseStatusException;

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

    /** LD-76: lỗi không lường trước trả JSON 500 chung, không lộ nội dung exception. */
    @Test
    void unexpectedErrorReturnsGenericJsonWithoutInternalDetails() {
        String internalMarker = "internal-detail-marker";

        ResponseEntity<ErrorResponse> response = new GlobalExceptionHandler()
                .handleUnexpected(new IllegalStateException(internalMarker));

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);
        assertThat(response.getBody().code()).isEqualTo("INTERNAL_ERROR");
        assertThat(response.getBody().message()).doesNotContain(internalMarker);
    }

    /** Lỗi của Spring đã có mã 4xx (ví dụ sai đường dẫn) giữ nguyên mã đó, không thành 500. */
    @Test
    void springClientErrorKeepsItsStatus() {
        ResponseEntity<ErrorResponse> response = new GlobalExceptionHandler()
                .handleUnexpected(new ResponseStatusException(HttpStatus.NOT_FOUND));

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(response.getBody().code()).isEqualTo("NOT_FOUND");
    }

    /** Lỗi khi gọi GitHub không có mã HTTP (GitHub từ chối đổi token) không hiện "HTTP 0". */
    @Test
    void gitHubErrorWithoutStatusDoesNotShowHttpZero() {
        ResponseEntity<ErrorResponse> response = new GlobalExceptionHandler()
                .handleGitHub(new GitHubApiException("GitHub OAuth token exchange was rejected.", false));

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_GATEWAY);
        assertThat(response.getBody().message()).doesNotContain("HTTP 0");
    }
}
