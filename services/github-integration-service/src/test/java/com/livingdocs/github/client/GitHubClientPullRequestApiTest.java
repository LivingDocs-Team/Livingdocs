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
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

/** LD-146: GitHubClient đọc Pull Request, file thay đổi (nhiều trang) và merge base từ HTTP server giả. */
class GitHubClientPullRequestApiTest {

    private HttpServer server;
    private GitHubClient client;
    private final List<String> queries = new CopyOnWriteArrayList<>();

    @BeforeEach
    void startServer() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.start();
        String baseUrl = "http://127.0.0.1:" + server.getAddress().getPort();
        client = new GitHubClient(new GitHubProperties("client-id", "client-secret", "livingdocs-test",
                "http://localhost:8082/api/github/callback", baseUrl, baseUrl), RestClient.builder());
    }

    @AfterEach
    void stopServer() {
        server.stop(0);
    }

    @Test
    void parsesPullRequest() {
        stub("/repos/acme/shop/pulls/7", 200, """
                {"number": 7, "title": "LD-146 currency", "body": "Fixes LD-147", "state": "open",
                 "html_url": "https://github.com/acme/shop/pull/7", "user": {"login": "dev1"},
                 "head": {"ref": "ld-146-currency", "sha": "%s"},
                 "base": {"ref": "main", "sha": "%s"}, "merged": false}
                """.formatted("h".repeat(40), "b".repeat(40)));

        GitHubPullRequest pr = client.getPullRequest("tok", "acme", "shop", 7);

        assertThat(pr.number()).isEqualTo(7);
        assertThat(pr.title()).isEqualTo("LD-146 currency");
        assertThat(pr.htmlUrl()).isEqualTo("https://github.com/acme/shop/pull/7");
        assertThat(pr.user().login()).isEqualTo("dev1");
        assertThat(pr.head().ref()).isEqualTo("ld-146-currency");
        assertThat(pr.base().sha()).isEqualTo("b".repeat(40));
    }

    @Test
    void readsAllPagesOfChangedFiles() {
        StringBuilder full = new StringBuilder("[");
        for (int i = 0; i < 100; i++) {
            full.append(i == 0 ? "" : ",").append("{\"filename\":\"src/f").append(i).append(".py\",\"status\":\"modified\"}");
        }
        full.append("]");
        String last = """
                [{"sha": "abc", "filename": "shop/utils.py", "status": "renamed",
                  "previous_filename": "shop/old_utils.py", "additions": 0, "deletions": 0, "changes": 0},
                 {"sha": "def", "filename": "shop/cart.py", "status": "modified", "additions": 1, "deletions": 1,
                  "changes": 2, "patch": "@@ -1 +1 @@\\n-a\\n+b"}]
                """;
        server.createContext("/repos/acme/shop/pulls/7/files", exchange -> {
            String query = exchange.getRequestURI().getRawQuery();
            queries.add(query);
            byte[] bytes = (query.endsWith("&page=1") ? full.toString() : last)
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });

        List<GitHubPullRequestFile> files = client.listPullRequestFiles("tok", "acme", "shop", 7);

        assertThat(files).hasSize(102);
        assertThat(queries).containsExactly("per_page=100&page=1", "per_page=100&page=2");
        GitHubPullRequestFile renamed = files.get(100);
        assertThat(renamed.previousFilename()).isEqualTo("shop/old_utils.py");
        assertThat(renamed.status()).isEqualTo("renamed");
        assertThat(files.get(101).patch()).isEqualTo("@@ -1 +1 @@\n-a\n+b");
    }

    @Test
    void readsMergeBaseAndKeepsNotFoundStatus() {
        String base = "b".repeat(40);
        String head = "h".repeat(40);
        stub("/repos/acme/shop/compare/", 200, """
                {"status": "ahead", "merge_base_commit": {"sha": "%s"}, "files": []}
                """.formatted("m".repeat(40)));
        stub("/repos/acme/shop/pulls/404", 404, "{\"message\": \"Not Found\"}");

        assertThat(client.getMergeBase("tok", "acme", "shop", base, head)).isEqualTo("m".repeat(40));
        Throwable error = catchThrowable(() -> client.getPullRequest("tok", "acme", "shop", 404));
        assertThat(error).isInstanceOf(GitHubApiException.class);
        assertThat(((GitHubApiException) error).isNotFound()).isTrue();
    }

    private void stub(String path, int status, String body) {
        server.createContext(path, exchange -> {
            exchange.getResponseHeaders().add("Content-Type", "application/json; charset=utf-8");
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });
    }
}



