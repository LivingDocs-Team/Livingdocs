package com.livingdocs.github;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.List;
import java.util.UUID;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.startsWith;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.http.HttpMethod.GET;
import static org.springframework.http.HttpMethod.POST;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.jsonPath;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import org.springframework.web.client.RestClient;

import com.fasterxml.jackson.databind.JsonNode;
import com.livingdocs.github.client.GitHubBlob;
import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.client.GitHubCommit;
import com.livingdocs.github.client.GitHubPullRequest;
import com.livingdocs.github.client.GitHubPullRequestFile;
import com.livingdocs.github.client.GitHubTree;
import com.livingdocs.github.dto.DriftAnalysisRequest;
import com.livingdocs.github.entity.ConnectedRepository;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.exception.GitHubApiException;
import com.livingdocs.github.service.DriftAnalysisService;
import com.livingdocs.github.service.GitHubConnectionService;
import com.livingdocs.github.service.RepositorySyncService;

/**
 * LD-150: phân tích lệch tài liệu thủ công (LD-145) trong github-integration-service.
 * GitHub được mock; code-analyzer và ai-service được giả lập bằng MockRestServiceServer.
 */
@ExtendWith(MockitoExtension.class)
class DriftAnalysisServiceTest {

    private static final String USER_ID = "drift-user";
    private static final UUID REPOSITORY_ID = UUID.fromString("22222222-2222-2222-2222-222222222222");
    private static final String TOKEN = "gho_test";
    private static final String HEAD = "h".repeat(40);
    private static final String BASE = "b".repeat(40);
    private static final String MERGE_BASE = "m".repeat(40);

    private static final String OLD_CODE = "def total(cart_id: int, discount: float) -> float:\n    return 1.0\n";
    private static final String NEW_CODE = "def total(cart_id: int, currency: str) -> float:\n    return 1.0\n";
    private static final String README = "# Shop\n\nCall `total(cart_id, discount)` for a cart total.\n";
    private static final String PATCH = """
            @@ -1,2 +1,2 @@
            -def total(cart_id: int, discount: float) -> float:
            +def total(cart_id: int, currency: str) -> float:
                 return 1.0""";

    private static final String ANALYSIS_BEFORE = """
            {"scope":"repository","target":"acme/shop","files":[{"path":"shop/cart.py","language":"python",
             "status":"ok","functions":[{"name":"total","parameters":[{"name":"cart_id","type":"int"},
             {"name":"discount","type":"float"}],"return_type":"float"}]}]}
            """;
    private static final String ANALYSIS_AFTER = """
            {"scope":"repository","target":"acme/shop","files":[{"path":"shop/cart.py","language":"python",
             "status":"ok","functions":[{"name":"total","parameters":[{"name":"cart_id","type":"int"},
             {"name":"currency","type":"str"}],"return_type":"float"}]}]}
            """;
    private static final String DOCUMENTS = """
            [{"id":"doc-shop","title":"Shop","target":"acme/shop"},
             {"id":"doc-other","title":"Other","target":"other/repo"}]
            """;
    private static final String REPORT = """
            {"id":"report-1","status":"drift_detected","repository":"acme/shop",
             "summary":{"findings":1,"highest_severity":"high"},
             "findings":[{"id":"F1","type":"signature","severity":"high","entity":"total"}],
             "warnings":["from ai-service"]}
            """;

    @Mock
    private RepositorySyncService repositorySyncService;
    @Mock
    private GitHubConnectionService connectionService;
    @Mock
    private GitHubClient gitHubClient;

    private MockRestServiceServer analyzerServer;
    private MockRestServiceServer aiServiceServer;
    private DriftAnalysisService driftService;
    private GitHubConnection connection;

    @BeforeEach
    void setUp() {
        RestClient.Builder analyzerBuilder = RestClient.builder();
        analyzerServer = MockRestServiceServer.bindTo(analyzerBuilder).build();
        RestClient.Builder aiBuilder = RestClient.builder();
        aiServiceServer = MockRestServiceServer.bindTo(aiBuilder).build();
        driftService = new DriftAnalysisService(repositorySyncService, connectionService, gitHubClient,
                analyzerBuilder.baseUrl("http://analyzer.test").build(), aiBuilder.baseUrl("http://ai.test").build());

        ConnectedRepository repository = new ConnectedRepository();
        repository.setFullName("acme/shop");
        connection = new GitHubConnection();
        connection.setAccessToken(TOKEN);
        lenient().when(repositorySyncService.requireOwned(USER_ID, REPOSITORY_ID)).thenReturn(repository);
        lenient().when(connectionService.getActiveConnection(USER_ID)).thenReturn(connection);
    }

    @Test
    void sendsPullRequestWithAnalyzerResultsAndRepositoryMarkdownToAiService() {
        stubGitHub();
        expectAnalyzer(ANALYSIS_BEFORE, ANALYSIS_AFTER);
        expectDocuments();
        aiServiceServer.expect(requestTo("http://ai.test/drift/analyze"))
                .andExpect(method(POST))
                .andExpect(content().json("""
                        {"repository":"acme/shop",
                         "pull_request":{"number":7,"title":"LD-146 Cart currency","author":"dev1",
                                         "head_branch":"ld-146-currency","base_branch":"main",
                                         "head_sha":"%s","base_sha":"%s",
                                         "url":"https://github.com/acme/shop/pull/7"},
                         "document_ids":["doc-shop"]}
                        """.formatted(HEAD, MERGE_BASE)))
                .andExpect(jsonPath("$.files.length()").value(2))
                .andExpect(jsonPath("$.files[0].path").value("shop/cart.py"))
                .andExpect(jsonPath("$.files[0].status").value("modified"))
                .andExpect(jsonPath("$.files[0].patch").value(PATCH))
                .andExpect(jsonPath("$.files[0].before.functions[0].parameters[1].name").value("discount"))
                .andExpect(jsonPath("$.files[0].after.functions[0].parameters[1].name").value("currency"))
                .andExpect(jsonPath("$.files[1].path").value("web/app.js"))
                .andExpect(jsonPath("$.files[1].before").doesNotExist())
                .andExpect(jsonPath("$.docs.length()").value(1))
                .andExpect(jsonPath("$.docs[0].path").value("README.md"))
                .andExpect(jsonPath("$.docs[0].content").value(README))
                .andRespond(withStatus(HttpStatus.CREATED).contentType(MediaType.APPLICATION_JSON).body(REPORT));

        JsonNode report = driftService.analyzePullRequest(USER_ID, REPOSITORY_ID,
                new DriftAnalysisRequest(7, null, null));

        assertEquals("report-1", report.path("id").asText());
        assertEquals("drift_detected", report.path("status").asText());
        assertEquals("from ai-service", report.path("warnings").get(0).asText());
        analyzerServer.verify();
        aiServiceServer.verify();
        verify(gitHubClient, never()).getBlob(TOKEN, "acme", "shop", "js-head");   // .js is not analyzed
    }

    @Test
    void checksOnlyDocumentsOfThisRepository() {
        stubGitHub();
        expectAnalyzer(ANALYSIS_BEFORE, ANALYSIS_AFTER);
        expectDocuments();
        aiServiceServer.expect(requestTo("http://ai.test/drift/analyze"))
                .andExpect(jsonPath("$.document_ids.length()").value(1))
                .andExpect(jsonPath("$.document_ids[0]").value("doc-shop"))
                .andExpect(jsonPath("$.docs.length()").value(0))
                .andRespond(withStatus(HttpStatus.CREATED).contentType(MediaType.APPLICATION_JSON).body(REPORT));

        JsonNode report = driftService.analyzePullRequest(USER_ID, REPOSITORY_ID,
                new DriftAnalysisRequest(7, List.of("doc-shop", "doc-other"), false));

        assertTrue(report.path("warnings").get(0).asText().contains("'doc-other' is not a document of acme/shop"));
        assertEquals("from ai-service", report.path("warnings").get(1).asText());
        aiServiceServer.verify();
    }

    @Test
    void analyzerFailureFallsBackToTheDiffWithAWarning() {
        stubGitHub();
        analyzerServer.expect(requestTo("http://analyzer.test/api/v1/analyze-repo")).andRespond(withServerError());
        analyzerServer.expect(requestTo("http://analyzer.test/api/v1/analyze-repo")).andRespond(withServerError());
        expectDocuments();
        aiServiceServer.expect(requestTo("http://ai.test/drift/analyze"))
                .andExpect(jsonPath("$.files[0].patch").value(PATCH))
                .andExpect(jsonPath("$.files[0].before").doesNotExist())
                .andExpect(jsonPath("$.files[0].after").doesNotExist())
                .andRespond(withStatus(HttpStatus.CREATED).contentType(MediaType.APPLICATION_JSON).body(REPORT));

        JsonNode report = driftService.analyzePullRequest(USER_ID, REPOSITORY_ID,
                new DriftAnalysisRequest(7, null, true));

        assertTrue(report.path("warnings").toString().contains("code analyzer could not analyze the base commit"));
        analyzerServer.verify();
        aiServiceServer.verify();
    }

    @Test
    void unknownPullRequestIsNotFound() {
        when(gitHubClient.getPullRequest(TOKEN, "acme", "shop", 404))
                .thenThrow(new GitHubApiException("GitHub API returned HTTP 404.", 404, null, "{}"));

        ApiException error = assertThrows(ApiException.class, () -> driftService.analyzePullRequest(
                USER_ID, REPOSITORY_ID, new DriftAnalysisRequest(404, null, null)));

        assertEquals(HttpStatus.NOT_FOUND, error.getStatus());
        assertEquals("PULL_REQUEST_NOT_FOUND", error.getCode());
        aiServiceServer.verify();
    }

    @Test
    void rejectedTokenMarksTheConnectionInvalid() {
        when(gitHubClient.getPullRequest(TOKEN, "acme", "shop", 7))
                .thenThrow(new GitHubApiException("GitHub API returned HTTP 401.", 401, null, "{}"));

        ApiException error = assertThrows(ApiException.class, () -> driftService.analyzePullRequest(
                USER_ID, REPOSITORY_ID, new DriftAnalysisRequest(7, null, null)));

        assertEquals("GITHUB_REAUTH_REQUIRED", error.getCode());
        verify(connectionService).markInvalid(connection);
    }

    @Test
    void pullRequestNumberIsRequired() {
        ApiException error = assertThrows(ApiException.class, () -> driftService.analyzePullRequest(
                USER_ID, REPOSITORY_ID, new DriftAnalysisRequest(null, null, null)));

        assertEquals(HttpStatus.BAD_REQUEST, error.getStatus());
        verify(gitHubClient, never()).getPullRequest(anyString(), anyString(), anyString(), anyInt());
    }

    @Test
    void aiServiceFailureIsBadGateway() {
        stubGitHub();
        expectAnalyzer(ANALYSIS_BEFORE, ANALYSIS_AFTER);
        expectDocuments();
        aiServiceServer.expect(requestTo("http://ai.test/drift/analyze")).andRespond(withServerError());

        ApiException error = assertThrows(ApiException.class, () -> driftService.analyzePullRequest(
                USER_ID, REPOSITORY_ID, new DriftAnalysisRequest(7, null, false)));

        assertEquals(HttpStatus.BAD_GATEWAY, error.getStatus());
        assertEquals("AI_SERVICE_FAILED", error.getCode());
    }

    @Test
    void reportsCanOnlyBeReadByTheirCreator() {
        stubGitHub();
        expectAnalyzer(ANALYSIS_BEFORE, ANALYSIS_AFTER);
        expectDocuments();
        aiServiceServer.expect(requestTo("http://ai.test/drift/analyze"))
                .andRespond(withStatus(HttpStatus.CREATED).contentType(MediaType.APPLICATION_JSON).body(REPORT));
        aiServiceServer.expect(requestTo(startsWith("http://ai.test/drift/reports?repository=")))
                .andExpect(method(GET))
                .andExpect(requestTo(containsString("pull_request=7")))
                .andRespond(withSuccess("""
                        [{"id":"report-1","status":"drift_detected"},{"id":"report-of-someone-else","status":"no_drift"}]
                        """, MediaType.APPLICATION_JSON));
        aiServiceServer.expect(requestTo("http://ai.test/drift/reports/report-1"))
                .andExpect(method(GET))
                .andRespond(withSuccess(REPORT, MediaType.APPLICATION_JSON));

        driftService.analyzePullRequest(USER_ID, REPOSITORY_ID, new DriftAnalysisRequest(7, null, false));
        JsonNode rows = driftService.listReports(USER_ID, REPOSITORY_ID, 7);
        JsonNode report = driftService.getReport(USER_ID, "report-1");
        ApiException other = assertThrows(ApiException.class,
                () -> driftService.getReport("another-user", "report-1"));
        ApiException unknown = assertThrows(ApiException.class,
                () -> driftService.getReport(USER_ID, "report-unknown"));

        assertEquals(1, rows.size());
        assertEquals("report-1", rows.get(0).path("id").asText());
        assertEquals("F1", report.path("findings").get(0).path("id").asText());
        assertEquals(HttpStatus.FORBIDDEN, other.getStatus());
        assertEquals(HttpStatus.NOT_FOUND, unknown.getStatus());
        aiServiceServer.verify();
    }

    // ------------------------------------------------------------------ fixtures

    /** PR #7: shop/cart.py modified (Python, analyzed) and web/app.js modified (not analyzed). */
    private void stubGitHub() {
        when(gitHubClient.getPullRequest(TOKEN, "acme", "shop", 7)).thenReturn(new GitHubPullRequest(
                7, "LD-146 Cart currency", "Adds currency.", "open", "https://github.com/acme/shop/pull/7",
                new GitHubPullRequest.Account("dev1"),
                new GitHubPullRequest.Ref("ld-146-currency", HEAD), new GitHubPullRequest.Ref("main", BASE)));
        when(gitHubClient.listPullRequestFiles(TOKEN, "acme", "shop", 7)).thenReturn(List.of(
                new GitHubPullRequestFile("py-head", "shop/cart.py", "modified", 1, 1, 2, PATCH, null),
                new GitHubPullRequestFile("js-head", "web/app.js", "modified", 1, 1, 2, "@@ -1 +1 @@\n-a\n+b", null)));
        when(gitHubClient.getMergeBase(TOKEN, "acme", "shop", BASE, HEAD)).thenReturn(MERGE_BASE);
        lenient().when(gitHubClient.getCommit(TOKEN, "acme", "shop", MERGE_BASE)).thenReturn(commit("tree-base"));
        lenient().when(gitHubClient.getCommit(TOKEN, "acme", "shop", HEAD)).thenReturn(commit("tree-head"));
        lenient().when(gitHubClient.getTree(TOKEN, "acme", "shop", "tree-base")).thenReturn(new GitHubTree(
                "tree-base", false, List.of(blob("shop/cart.py", "py-base"), blob("web/app.js", "js-base"))));
        lenient().when(gitHubClient.getTree(TOKEN, "acme", "shop", "tree-head")).thenReturn(new GitHubTree(
                "tree-head", false, List.of(blob("shop/cart.py", "py-head"), blob("web/app.js", "js-head"),
                        blob("README.md", "readme"), blob("node_modules/lib/README.md", "vendored"),
                        new GitHubTree.Entry("docs", "040000", "tree", "docs-tree", null))));
        lenient().when(gitHubClient.getBlob(TOKEN, "acme", "shop", "py-base")).thenReturn(blobOf("py-base", OLD_CODE));
        lenient().when(gitHubClient.getBlob(TOKEN, "acme", "shop", "py-head")).thenReturn(blobOf("py-head", NEW_CODE));
        lenient().when(gitHubClient.getBlob(TOKEN, "acme", "shop", "readme")).thenReturn(blobOf("readme", README));
    }

    private void expectAnalyzer(String before, String after) {
        analyzerServer.expect(requestTo("http://analyzer.test/api/v1/analyze-repo"))
                .andExpect(method(POST))
                .andExpect(content().json("""
                        {"scope":"repository","target":"acme/shop","files":[
                          {"path":"shop/cart.py","language":"python","content":%s}]}
                        """.formatted(quote(OLD_CODE))))
                .andRespond(withSuccess(before, MediaType.APPLICATION_JSON));
        analyzerServer.expect(requestTo("http://analyzer.test/api/v1/analyze-repo"))
                .andExpect(content().json("""
                        {"files":[{"path":"shop/cart.py","content":%s}]}
                        """.formatted(quote(NEW_CODE))))
                .andRespond(withSuccess(after, MediaType.APPLICATION_JSON));
    }

    private void expectDocuments() {
        aiServiceServer.expect(requestTo("http://ai.test/documents"))
                .andExpect(method(GET))
                .andRespond(withSuccess(DOCUMENTS, MediaType.APPLICATION_JSON));
    }

    private static GitHubCommit commit(String treeSha) {
        return new GitHubCommit("sha", null,
                new GitHubCommit.Detail("msg", null, null, new GitHubCommit.TreeRef(treeSha)), null);
    }

    private static GitHubTree.Entry blob(String path, String sha) {
        return new GitHubTree.Entry(path, "100644", "blob", sha, 100L);
    }

    private static GitHubBlob blobOf(String sha, String text) {
        return new GitHubBlob(sha, (long) text.length(), "base64",
                Base64.getEncoder().encodeToString(text.getBytes(StandardCharsets.UTF_8)));
    }

    private static String quote(String text) {
        return "\"" + text.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n") + "\"";
    }
}
