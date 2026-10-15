package com.livingdocs.github.client;

import com.livingdocs.github.config.GitHubProperties;
import com.livingdocs.github.exception.GitHubApiException;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

/**
 * Kiểm tra GitHubClient đọc đúng JSON GitHub trả về và giữ đúng mã lỗi,
 * bằng một HTTP server giả chạy trên máy (không gọi GitHub thật).
 */
class GitHubClientRepositoryApiTest {

    private HttpServer server;
    private GitHubClient client;
    private final AtomicReference<String> lastAuthorization = new AtomicReference<>();
    private final AtomicReference<String> lastQuery = new AtomicReference<>();

    @BeforeEach
    void startServer() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.start();
        String baseUrl = "http://127.0.0.1:" + server.getAddress().getPort();
        GitHubProperties props = new GitHubProperties("client-id", "client-secret", "livingdocs-test",
                "http://localhost:8082/api/github/callback", baseUrl, baseUrl);
        client = new GitHubClient(props, RestClient.builder());
    }

    @AfterEach
    void stopServer() {
        server.stop(0);
    }

    @Test
    void parsesRepositoryDetails() {
        stub("/repos/LivingDocs-Team/Livingdocs", 200, """
                {"id": 101, "name": "Livingdocs", "full_name": "LivingDocs-Team/Livingdocs",
                 "owner": {"login": "LivingDocs-Team", "id": 5},
                 "description": "BLCK", "private": false, "archived": false, "disabled": false,
                 "default_branch": "main", "html_url": "https://github.com/LivingDocs-Team/Livingdocs",
                 "language": "Java", "size": 2048, "pushed_at": "2026-10-12T08:30:00Z", "forks": 0}
                """, Map.of());

        GitHubRepoDetails repo = client.getRepositoryDetails("tok", "LivingDocs-Team", "Livingdocs");

        assertThat(repo.id()).isEqualTo(101L);
        assertThat(repo.fullName()).isEqualTo("LivingDocs-Team/Livingdocs");
        assertThat(repo.owner().login()).isEqualTo("LivingDocs-Team");
        assertThat(repo.privateRepo()).isFalse();
        assertThat(repo.defaultBranch()).isEqualTo("main");
        assertThat(repo.pushedAt()).isEqualTo(Instant.parse("2026-10-12T08:30:00Z"));
        assertThat(lastAuthorization.get()).isEqualTo("Bearer tok");
    }

    @Test
    void parsesCommitTreeBlobLanguagesAndCommitList() {
        String sha = "a".repeat(40);
        String treeSha = "b".repeat(40);
        String blobSha = "d".repeat(40);
        String commitJson = """
                {"sha": "%s", "html_url": "https://github.com/o/r/commit/%s",
                 "commit": {"message": "LD-63 sync", "tree": {"sha": "%s"},
                            "author": {"name": "Hai", "email": "h@x.com", "date": "2026-10-12T09:00:00Z"},
                            "committer": {"name": "GitHub", "email": "noreply@github.com", "date": "2026-10-12T09:01:00Z"}},
                 "author": {"login": "d3r-bbb"}}
                """.formatted(sha, sha, treeSha);
        stub("/repos/o/r/commits/main", 200, commitJson, Map.of());
        stub("/repos/o/r/git/trees/" + treeSha, 200, """
                {"sha": "%s", "truncated": false, "tree": [
                  {"path": "src", "mode": "040000", "type": "tree", "sha": "%s"},
                  {"path": "src/App.java", "mode": "100644", "type": "blob", "sha": "%s", "size": 42}
                ]}
                """.formatted(treeSha, "c".repeat(40), blobSha), Map.of());
        stub("/repos/o/r/git/blobs/" + blobSha, 200, """
                {"sha": "%s", "size": 12, "encoding": "base64", "content": "Y2xhc3MgQXBw\\nIHt9Cg==\\n"}
                """.formatted(blobSha), Map.of());
        stub("/repos/o/r/languages", 200, "{\"Java\": 900, \"Python\": 30}", Map.of());
        stub("/repos/o/r/commits", 200, "[" + commitJson + "]", Map.of());

        GitHubCommit commit = client.getCommit("tok", "o", "r", "main");
        assertThat(commit.sha()).isEqualTo(sha);
        assertThat(commit.commit().tree().sha()).isEqualTo(treeSha);
        assertThat(commit.commit().author().date()).isEqualTo(Instant.parse("2026-10-12T09:00:00Z"));
        assertThat(commit.author().login()).isEqualTo("d3r-bbb");

        GitHubTree tree = client.getTree("tok", "o", "r", treeSha);
        assertThat(tree.truncated()).isFalse();
        assertThat(tree.tree()).extracting(GitHubTree.Entry::path).containsExactly("src", "src/App.java");
        assertThat(tree.tree().get(1).size()).isEqualTo(42L);
        assertThat(lastQuery.get()).isEqualTo("recursive=1");

        GitHubBlob blob = client.getBlob("tok", "o", "r", blobSha);
        assertThat(blob.encoding()).isEqualTo("base64");
        assertThat(blob.content()).contains("\n"); // GitHub xuống dòng trong base64, phải giải mã bằng MIME decoder

        Map<String, Long> languages = client.getLanguages("tok", "o", "r");
        assertThat(languages).containsExactly(Map.entry("Java", 900L), Map.entry("Python", 30L));

        List<GitHubCommit> commits = client.listCommits("tok", "o", "r", "main", 5);
        assertThat(commits).hasSize(1);
        assertThat(lastQuery.get()).contains("sha=main").contains("per_page=5");
    }

    @Test
    void notFound_keepsStatusCode() {
        stub("/repos/o/missing", 404, "{\"message\": \"Not Found\"}", Map.of());

        GitHubApiException e = failure(() -> client.getRepositoryDetails("tok", "o", "missing"));

        assertThat(e.getStatusCode()).isEqualTo(404);
        assertThat(e.isNotFound()).isTrue();
        assertThat(e.isRateLimited()).isFalse();
    }

    @Test
    void rateLimit_isDetectedFromHeaders() {
        stub("/repos/o/r", 403, "{\"message\": \"API rate limit exceeded\"}",
                Map.of("x-ratelimit-remaining", "0", "x-ratelimit-reset", "1791000000"));

        GitHubApiException e = failure(() -> client.getRepositoryDetails("tok", "o", "r"));

        assertThat(e.getStatusCode()).isEqualTo(403);
        assertThat(e.isRateLimited()).isTrue();
        assertThat(e.retryAt()).isEqualTo(Instant.ofEpochSecond(1791000000));
    }

    @Test
    void forbiddenWithoutRateLimit_isNotRateLimited() {
        stub("/repos/o/private", 403, "{\"message\": \"Resource not accessible by integration\"}",
                Map.of("x-ratelimit-remaining", "4999"));

        GitHubApiException e = failure(() -> client.getRepositoryDetails("tok", "o", "private"));

        assertThat(e.isRateLimited()).isFalse();
        assertThat(e.getStatusCode()).isEqualTo(403);
    }

    @Test
    void unauthorized_isDetected() {
        stub("/repos/o/r", 401, "{\"message\": \"Bad credentials\"}", Map.of("WWW-Authenticate", "Bearer"));

        GitHubApiException e = failure(() -> client.getRepositoryDetails("bad-token", "o", "r"));

        assertThat(e.isUnauthorized()).isTrue();
    }

    @Test
    void withoutToken_sendsNoAuthorizationHeader() {
        stub("/repos/o/r/languages", 200, "{}", Map.of());

        client.getLanguages(null, "o", "r");

        assertThat(lastAuthorization.get()).isNull();
    }

    private static GitHubApiException failure(org.assertj.core.api.ThrowableAssert.ThrowingCallable call) {
        Throwable thrown = catchThrowable(call);
        assertThat(thrown).isInstanceOf(GitHubApiException.class);
        return (GitHubApiException) thrown;
    }

    private void stub(String path, int status, String body, Map<String, String> headers) {
        server.createContext(path, exchange -> {
            lastAuthorization.set(exchange.getRequestHeaders().getFirst("Authorization"));
            lastQuery.set(exchange.getRequestURI().getRawQuery());
            headers.forEach((name, value) -> exchange.getResponseHeaders().add(name, value));
            exchange.getResponseHeaders().add("Content-Type", "application/json; charset=utf-8");
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });
    }
}
