package com.livingdocs.github.controller;

import com.livingdocs.github.dto.CallbackResponse;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.exception.GitHubApiException;
import com.livingdocs.github.service.GitHubConnectionService;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/** Callback của GitHub: trả JSON, hoặc chuyển người dùng về frontend khi có FRONTEND_URL. */
class GitHubConnectionControllerTest {

    private static final String FRONTEND = "http://localhost:3000/";

    private final GitHubConnectionService service = mock(GitHubConnectionService.class);

    @Test
    void withoutFrontendUrl_returnsJson() {
        when(service.handleCallback("code-1", "state-1")).thenReturn(connection("d3r-bbb"));

        ResponseEntity<CallbackResponse> response =
                new GitHubConnectionController(service, "").callback("code-1", "state-1", null);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody().githubLogin()).isEqualTo("d3r-bbb");
    }

    @Test
    void success_redirectsToFrontend() {
        when(service.handleCallback("code-1", "state-1")).thenReturn(connection("d3r-bbb"));

        ResponseEntity<CallbackResponse> response =
                new GitHubConnectionController(service, FRONTEND).callback("code-1", "state-1", null);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.FOUND);
        assertThat(response.getHeaders().getLocation())
                .hasToString("http://localhost:3000/?github=connected&login=d3r-bbb");
    }

    @Test
    void invalidState_redirectsWithErrorCode() {
        when(service.handleCallback("code-1", "gia-mao"))
                .thenThrow(ApiException.badRequest("State không hợp lệ hoặc đã hết hạn."));

        ResponseEntity<CallbackResponse> response =
                new GitHubConnectionController(service, FRONTEND).callback("code-1", "gia-mao", null);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.FOUND);
        assertThat(response.getHeaders().getLocation())
                .hasToString("http://localhost:3000/?github=error&reason=BAD_REQUEST");
    }

    @Test
    void gitHubError_redirectsWithErrorCode() {
        when(service.handleCallback("code-het-han", "state-1"))
                .thenThrow(new GitHubApiException("bad_verification_code", false));

        ResponseEntity<CallbackResponse> response =
                new GitHubConnectionController(service, FRONTEND).callback("code-het-han", "state-1", null);

        assertThat(response.getHeaders().getLocation())
                .hasToString("http://localhost:3000/?github=error&reason=GITHUB_API_ERROR");
    }

    @Test
    void userCancelledOnGitHub_redirectsWithAccessDenied() {
        ResponseEntity<CallbackResponse> response =
                new GitHubConnectionController(service, FRONTEND).callback(null, "state-1", "access_denied");

        assertThat(response.getHeaders().getLocation())
                .hasToString("http://localhost:3000/?github=error&reason=GITHUB_ACCESS_DENIED");
        verify(service, never()).handleCallback(any(), any());
    }

    @Test
    void userCancelledOnGitHub_withoutFrontendUrl_isBadRequest() {
        GitHubConnectionController controller = new GitHubConnectionController(service, "");

        assertThatThrownBy(() -> controller.callback(null, "state-1", "access_denied"))
                .isInstanceOf(ApiException.class)
                .hasFieldOrPropertyWithValue("code", "GITHUB_ACCESS_DENIED");
        verify(service, never()).handleCallback(any(), any());
    }

    private static GitHubConnection connection(String login) {
        GitHubConnection connection = new GitHubConnection();
        connection.setGithubLogin(login);
        return connection;
    }
}
