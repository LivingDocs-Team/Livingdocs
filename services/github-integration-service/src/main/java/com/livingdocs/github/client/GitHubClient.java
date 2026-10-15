package com.livingdocs.github.client;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.livingdocs.github.config.GitHubProperties;
import com.livingdocs.github.exception.GitHubApiException;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;
import java.util.function.Supplier;

/**
 * Tất cả lời gọi tới GitHub nằm ở đây, để dễ thay bằng mock khi viết test.
 */
@Component
public class GitHubClient {

    private static final int PER_PAGE = 100;
    private static final int MAX_PAGES = 10;
    private static final int MAX_ERROR_BODY_IN_MESSAGE = 300;

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

    // ------------------------------------------------------------------ OAuth (Epic 2)

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
                .headers(auth(accessToken))
                .retrieve()
                .body(GitHubUser.class));
    }

    /** Thu hồi quyền LivingDocs trên tài khoản GitHub của người dùng. Lỗi thì bỏ qua (best-effort). */
    public void revokeGrant(String accessToken) {
        try {
            apiClient.method(HttpMethod.DELETE)
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

    // ------------------------------------------------------------------ Repository list (Epic 3)

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
                        .headers(auth(accessToken))
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
                .headers(auth(accessToken))
                .retrieve()
                .body(GitHubRepo.class));
    }

    // ------------------------------------------------------------------ Repository sync (LD-63)

    /** Thông tin đầy đủ của repo (mô tả, nhánh mặc định, archived, ngôn ngữ chính...). */
    public GitHubRepoDetails getRepositoryDetails(String accessToken, String owner, String repo) {
        return call(() -> apiClient.get().uri("/repos/{owner}/{repo}", owner, repo)
                .headers(auth(accessToken))
                .retrieve()
                .body(GitHubRepoDetails.class));
    }

    /** Commit mới nhất của một nhánh (ref = tên nhánh, tag hoặc SHA). Repo rỗng: GitHub trả 409. */
    public GitHubCommit getCommit(String accessToken, String owner, String repo, String ref) {
        return call(() -> apiClient.get().uri("/repos/{owner}/{repo}/commits/{ref}", owner, repo, ref)
                .headers(auth(accessToken))
                .retrieve()
                .body(GitHubCommit.class));
    }

    /** Toàn bộ cây thư mục (đệ quy) của một tree SHA, chỉ 1 lần gọi API. */
    public GitHubTree getTree(String accessToken, String owner, String repo, String treeSha) {
        return call(() -> apiClient.get().uri("/repos/{owner}/{repo}/git/trees/{sha}?recursive=1", owner, repo, treeSha)
                .headers(auth(accessToken))
                .retrieve()
                .body(GitHubTree.class));
    }

    /** Nội dung một file theo SHA (không đổi theo thời gian nên luôn khớp với commit đang đồng bộ). */
    public GitHubBlob getBlob(String accessToken, String owner, String repo, String blobSha) {
        return call(() -> apiClient.get().uri("/repos/{owner}/{repo}/git/blobs/{sha}", owner, repo, blobSha)
                .headers(auth(accessToken))
                .retrieve()
                .body(GitHubBlob.class));
    }

    /** Số byte code theo từng ngôn ngữ, ví dụ {"Java": 12000, "Python": 3400}. */
    public Map<String, Long> getLanguages(String accessToken, String owner, String repo) {
        Map<String, Long> result = call(() -> apiClient.get().uri("/repos/{owner}/{repo}/languages", owner, repo)
                .headers(auth(accessToken))
                .retrieve()
                .body(new ParameterizedTypeReference<LinkedHashMap<String, Long>>() {
                }));
        return result == null ? Map.of() : result;
    }

    /** Các commit gần nhất của một nhánh, mới nhất trước. limit tối đa 100. */
    public List<GitHubCommit> listCommits(String accessToken, String owner, String repo, String ref, int limit) {
        int perPage = Math.max(1, Math.min(limit, PER_PAGE));
        List<GitHubCommit> result = call(() -> apiClient.get()
                .uri("/repos/{owner}/{repo}/commits?sha={ref}&per_page={pp}", owner, repo, ref, perPage)
                .headers(auth(accessToken))
                .retrieve()
                .body(new ParameterizedTypeReference<List<GitHubCommit>>() {
                }));
        return result == null ? List.of() : result;
    }

    // ------------------------------------------------------------------ helpers

    private List<Installation> listInstallations(String accessToken) {
        Installations installations = call(() -> apiClient.get()
                .uri("/user/installations?per_page={pp}", PER_PAGE)
                .headers(auth(accessToken))
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

    /**
     * Gắn token vào header Authorization. Không có token thì gọi ẩn danh
     * (chỉ đọc được repo public, giới hạn 60 lần gọi/giờ) - dùng cho test với repo public.
     */
    private static Consumer<HttpHeaders> auth(String accessToken) {
        return headers -> {
            if (accessToken != null && !accessToken.isBlank()) {
                headers.setBearerAuth(accessToken);
            }
        };
    }

    private <T> T call(Supplier<T> request) {
        try {
            return request.get();
        } catch (RestClientResponseException e) {
            int status = e.getStatusCode().value();
            String body = e.getResponseBodyAsString();
            String shortBody = body.length() > MAX_ERROR_BODY_IN_MESSAGE
                    ? body.substring(0, MAX_ERROR_BODY_IN_MESSAGE) + "..."
                    : body;
            throw new GitHubApiException("GitHub API trả lỗi " + status + ": " + shortBody,
                    status, e.getResponseHeaders(), body);
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
