package com.livingdocs.github;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.dto.RepositoryResponse;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.service.RepositoryManagementService;
import com.livingdocs.github.service.RepositorySyncService;
import com.livingdocs.github.sync.RepositorySnapshot;
import com.livingdocs.github.sync.RepositorySnapshot.SourceFile;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/** Exercises the actual HTTP endpoint, security filter, search service and analyzer HTTP client. */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class DocumentationSearchHttpIntegrationTest {
    private static final UUID REPOSITORY_ID = UUID.fromString("11111111-1111-1111-1111-111111111111");
    private static final UUID OTHER_REPOSITORY_ID = UUID.fromString("22222222-2222-2222-2222-222222222222");
    private static final String USER_ID = "search-http-user";
    private static final String ANALYSIS_JSON = """
            {"files":[{"path":"src/Checkout.java","language":"java","classes":[
              {"name":"CheckoutService","kind":"class","docstring":"Handles checkout requests.","lineno":8,"methods":[]}
            ],"functions":[],"endpoints":[]}]}
            """;

    private static final AtomicInteger ANALYZER_CALLS = new AtomicInteger();
    private static final AtomicReference<String> ANALYZER_REQUEST = new AtomicReference<>("");
    private static final ExecutorService ANALYZER_EXECUTOR = Executors.newCachedThreadPool(task -> {
        Thread thread = new Thread(task, "search-analyzer-test-http");
        thread.setDaemon(true);
        return thread;
    });
    private static final HttpServer ANALYZER_SERVER = startAnalyzerServer();

    @DynamicPropertySource
    static void configureAnalyzer(DynamicPropertyRegistry properties) {
        properties.add("services.code-analyzer.base-url",
                () -> "http://127.0.0.1:" + ANALYZER_SERVER.getAddress().getPort());
    }

    @Autowired private TestRestTemplate http;
    @Autowired private ObjectMapper objectMapper;
    @LocalServerPort private int port;

    @MockitoBean private RepositoryManagementService repositoryService;
    @MockitoBean private RepositorySyncService syncService;

    @BeforeEach
    void setUp() {
        ANALYZER_CALLS.set(0);
        ANALYZER_REQUEST.set("");
        when(repositoryService.get(USER_ID, REPOSITORY_ID)).thenReturn(repository());
        when(syncService.latestOrSync(USER_ID, REPOSITORY_ID)).thenReturn(snapshot());
    }

    @AfterAll
    static void stopAnalyzer() {
        ANALYZER_SERVER.stop(0);
        ANALYZER_EXECUTOR.shutdownNow();
    }

    @Test
    void searchesOverHttpReturnsActualResultsAndEnforcesRepositoryIsolation() throws Exception {
        ResponseEntity<JsonNode> response = get(searchUrl(REPOSITORY_ID, "checkout"), true);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        JsonNode body = response.getBody();
        assertThat(body.path("query").asText()).isEqualTo("checkout");
        assertThat(body.path("total").asInt()).isEqualTo(2);
        assertThat(body.path("results").size()).isEqualTo(2);
        JsonNode documentation = body.path("results").get(0);
        assertThat(documentation.path("type").asText()).isEqualTo("documentation");
        assertThat(documentation.path("repositoryId").asText()).isEqualTo(REPOSITORY_ID.toString());
        assertThat(documentation.path("repositoryName").asText()).isEqualTo("acme/shop");
        assertThat(documentation.path("path").asText()).isEqualTo("src/Checkout.java");
        assertThat(documentation.path("line").asInt()).isEqualTo(8);
        assertThat(documentation.path("score").asInt()).isPositive();
        assertThat(documentation.path("url").asText())
                .isEqualTo("https://github.com/acme/shop/blob/main/src/Checkout.java#L8");
        assertThat(body.path("results").get(1).path("type").asText()).isEqualTo("code");

        JsonNode analyzerRequest = objectMapper.readTree(ANALYZER_REQUEST.get());
        assertThat(analyzerRequest.path("target").asText()).isEqualTo("acme/shop");
        assertThat(analyzerRequest.path("files").get(0).path("path").asText()).isEqualTo("src/Checkout.java");
        assertThat(ANALYZER_CALLS).hasValue(1);

        ResponseEntity<JsonNode> noResults = get(searchUrl(REPOSITORY_ID, "no-such-symbol"), true);
        assertThat(noResults.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(noResults.getBody().path("total").asInt()).isZero();
        assertThat(noResults.getBody().path("results").size()).isZero();
        assertThat(ANALYZER_CALLS).hasValue(1); // analyzed snapshot reused for the same commit

        when(repositoryService.get(USER_ID, OTHER_REPOSITORY_ID))
                .thenThrow(ApiException.forbidden("Repository belongs to another user."));
        ResponseEntity<JsonNode> forbidden = get(searchUrl(OTHER_REPOSITORY_ID, "checkout"), true);
        assertThat(forbidden.getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(ANALYZER_CALLS).hasValue(1);

        ResponseEntity<JsonNode> unauthorized = get(searchUrl(REPOSITORY_ID, "checkout"), false);
        assertThat(unauthorized.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(ANALYZER_CALLS).hasValue(1);
        verify(syncService, times(2)).latestOrSync(USER_ID, REPOSITORY_ID);
        verify(syncService, never()).latestOrSync(USER_ID, OTHER_REPOSITORY_ID);
    }

    private ResponseEntity<JsonNode> get(String url, boolean trustedService) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-User-Id", USER_ID);
        if (trustedService) headers.setBearerAuth("test-only-internal-credential");
        return http.exchange(url, HttpMethod.GET, new HttpEntity<>(headers), JsonNode.class);
    }

    private String searchUrl(UUID repositoryId, String query) {
        return "http://127.0.0.1:" + port + "/api/repositories/" + repositoryId
                + "/documentation/search?q=" + query;
    }

    private static RepositoryResponse repository() {
        return new RepositoryResponse(REPOSITORY_ID, "ws-search-http-user", 42L,
                "acme/shop", "main", false, "https://github.com/acme/shop", "CONNECTED", null, Instant.EPOCH);
    }

    private static RepositorySnapshot snapshot() {
        return new RepositorySnapshot(
                new RepositorySnapshot.RepositoryInfo(42L, "acme/shop", "acme", "shop", null,
                        false, false, "main", "https://github.com/acme/shop", "Java", 1L, null),
                "main", new RepositorySnapshot.CommitInfo("search-http-commit", "test", "user", "user",
                        Instant.EPOCH, "https://github.com/acme/shop/commit/search-http-commit"),
                Map.of(), List.of(new SourceFile("src/Checkout.java", "checkout-blob", 64L, "java",
                        "class CheckoutService {}", null)), List.of(),
                new RepositorySnapshot.SyncStats(1, 1, 1, 0, false, false), List.of(), Instant.EPOCH);
    }

    private static HttpServer startAnalyzerServer() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/api/v1/analyze-repo", DocumentationSearchHttpIntegrationTest::analyze);
            server.setExecutor(ANALYZER_EXECUTOR);
            server.start();
            return server;
        } catch (IOException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    private static void analyze(HttpExchange exchange) throws IOException {
        ANALYZER_CALLS.incrementAndGet();
        ANALYZER_REQUEST.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
        byte[] response = ANALYSIS_JSON.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(200, response.length);
        try (var output = exchange.getResponseBody()) {
            output.write(response);
        }
    }
}



