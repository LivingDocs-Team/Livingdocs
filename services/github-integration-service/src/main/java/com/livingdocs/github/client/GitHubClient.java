package com.livingdocs.github.client;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.livingdocs.github.config.GitHubProperties;
import com.livingdocs.github.exception.GitHubApiException;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Tất cả lời gọi tới GitHub nằm ở đây, để dễ thay bằng mock khi viết test.
 */
@Component
public class GitHubClient {

    private static final int PER_PAGE = 100;
    private static final int MAX_PAGES = 10;

    private final GitHubProperties props;
    private final RestClient oauthClient;
    private final RestClient apiClient;

    public GitHubClient(GitHubProperties props, RestClient.Builder builder) {
        this.props = props;
        this.oauthClient = builder.clone()
                .baseUrl(props.oauthBaseUrl())
                .defaultHeader("Accept", MediaType.APPLICATION_JSON_VALUE)
                .build();
        this.apiClient = builder.clone()
                .baseUrl(props.apiBaseUrl())
                .defaultHeader("Accept", "application/vnd.github+json")
                .defaultHeader("X-GitHub-Api-Version", "2022-11-28")
                .build();
    }

    /** Đổi "code" GitHub gửi về callback lấy access token + refresh token. */
    public GitHubTokenResponse exchangeCode(String code) {
        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("client_id", props.clientId());
        form.add("client_secret", props.clientSecret());
        form.add("code", code);
        form.add("redirect_uri", props.redirectUri());
        return postToken(form);
    }

    /** Lấy access token mới khi token cũ sắp hết hạn (token GitHub App sống khoảng 8 giờ). */
    public GitHubTokenResponse refreshToken(String refreshToken) {
        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("client_id", props.clientId());
        form.add("client_secret", props.clientSecret());
        form.add("grant_type", "refresh_token");
        form.add("refresh_token", refreshToken);
        return postToken(form);
    }

    public GitHubUser getAuthenticatedUser(String accessToken) {
        return call(() -> apiClient.get().uri("/user")
                .headers(h -> h.setBearerAuth(accessToken))
                .retrieve()
                .body(GitHubUser.class));
    }

    /**
     * Liệt kê các repo người dùng truy cập được THÔNG QUA GitHub App
     * (tức là các repo đã chọn khi cài app).
     */
    public List<GitHubRepo> listAccessibleRepositories(String accessToken) {
        List<GitHubRepo> result = new ArrayList<>();
        for (Installation installation : listInstallations(accessToken)) {
            for (int page = 1; page <= MAX_PAGES; page++) {
                final int p = page;
                InstallationRepos repos = call(() -> apiClient.get()
                        .uri("/user/installations/{id}/repositories?per_page={pp}&page={p}",
                                installation.id(), PER_PAGE, p)
                        .headers(h -> h.setBearerAuth(accessToken))
                        .retrieve()
                        .body(InstallationRepos.class));
                if (repos == null || repos.repositories() == null || repos.repositories().isEmpty()) {
                    break;
                }
                result.addAll(repos.repositories());
                if (repos.repositories().size() < PER_PAGE) {
                    break;
                }
            }
        }
        return result;
    }

    public GitHubRepo getRepository(String accessToken, String fullName) {
        String[] parts = fullName.split("/", 2);
        return call(() -> apiClient.get().uri("/repos/{owner}/{repo}", parts[0], parts[1])
                .headers(h -> h.setBearerAuth(accessToken))
                .retrieve()
                .body(GitHubRepo.class));
    }

    /** Thu hồi quyền LivingDocs trên tài khoản GitHub của người dùng. Lỗi thì bỏ qua (best-effort). */
    public void revokeGrant(String accessToken) {
        try {
            apiClient.method(org.springframework.http.HttpMethod.DELETE)
                    .uri("/applications/{clientId}/grant", props.clientId())
                    .headers(h -> h.setBasicAuth(props.clientId(), props.clientSecret()))
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("access_token", accessToken))
                    .retrieve()
                    .toBodilessEntity();
        } catch (RestClientException ignored) {
            // Token có thể đã hết hạn, không sao: phía LivingDocs vẫn xoá token.
        }
    }

    private List<Installation> listInstallations(String accessToken) {
        Installations installations = call(() -> apiClient.get()
                .uri("/user/installations?per_page={pp}", PER_PAGE)
                .headers(h -> h.setBearerAuth(accessToken))
                .retrieve()
                .body(Installations.class));
        if (installations == null || installations.installations() == null) {
            return List.of();
        }
        return installations.installations();
    }

    private GitHubTokenResponse postToken(MultiValueMap<String, String> form) {
        GitHubTokenResponse response = call(() -> oauthClient.post()
                .uri("/login/oauth/access_token")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(form)
                .retrieve()
                .body(GitHubTokenResponse.class));
        if (response == null) {
            throw new GitHubApiException("GitHub không trả về token", false);
        }
        if (response.error() != null) {
            // GitHub trả HTTP 200 kèm "error" khi code sai / hết hạn / đã dùng rồi.
            throw new GitHubApiException("GitHub từ chối: " + response.error()
                    + (response.errorDescription() != null ? " - " + response.errorDescription() : ""),
                    "bad_refresh_token".equals(response.error()));
        }
        return response;
    }

    private <T> T call(java.util.function.Supplier<T> request) {
        try {
            return request.get();
        } catch (RestClientResponseException e) {
            boolean unauthorized = e.getStatusCode().isSameCodeAs(HttpStatus.UNAUTHORIZED);
            throw new GitHubApiException("GitHub API trả lỗi " + e.getStatusCode().value()
                    + ": " + e.getResponseBodyAsString(), unauthorized);
        } catch (RestClientException e) {
            throw new GitHubApiException("Không gọi được GitHub API: " + e.getMessage(), e);
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Installation(Long id) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Installations(@JsonProperty("total_count") Integer totalCount, List<Installation> installations) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record InstallationRepos(@JsonProperty("total_count") Integer totalCount, List<GitHubRepo> repositories) {
    }
}
