package com.livingdocs.github;

import com.fasterxml.jackson.databind.JsonNode;
import com.livingdocs.github.dto.DocumentationGenerationRequest;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.service.DocumentationGenerationService;
import com.livingdocs.github.service.RepositorySyncService;
import com.livingdocs.github.sync.RepositorySnapshot;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.http.HttpStatus;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.http.HttpMethod.POST;
import static org.springframework.http.HttpMethod.GET;

@ExtendWith(MockitoExtension.class)
class DocumentationGenerationServiceTest {

    private static final String USER_ID = "integration-user";
    private static final UUID REPOSITORY_ID = UUID.fromString("11111111-1111-1111-1111-111111111111");
    private static final String ANALYSIS = """
            {"scope":"repository","target":"acme/shop","files":[
              {"path":"src/App.java","language":"java","status":"ok","classes":[],"functions":[],"endpoints":[]}
            ]}
            """;
    private static final String EXPECTED_AI_REQUEST = """
            {"scope":"repository","target":"acme/shop","template_id":"default","output_language":"en","files":[
              {"path":"src/App.java","language":"java","status":"ok","classes":[],"functions":[],"endpoints":[]}
            ]}
            """;

    @Mock
    private RepositorySyncService repositorySyncService;

    private MockRestServiceServer analyzerServer;
    private MockRestServiceServer aiServiceServer;
    private DocumentationGenerationService generationService;

    @BeforeEach
    void setUp() {
        RestClient.Builder analyzerBuilder = RestClient.builder();
        analyzerServer = MockRestServiceServer.bindTo(analyzerBuilder).build();
        RestClient analyzerClient = analyzerBuilder.baseUrl("http://analyzer.test").build();

        RestClient.Builder aiBuilder = RestClient.builder();
        aiServiceServer = MockRestServiceServer.bindTo(aiBuilder).build();
        RestClient aiClient = aiBuilder.baseUrl("http://ai.test").build();

        generationService = new DocumentationGenerationService(
                repositorySyncService, analyzerClient, aiClient);
        when(repositorySyncService.latest(USER_ID, REPOSITORY_ID)).thenReturn(snapshot());
    }

    @Test
    void analyzesLatestAuthorizedSnapshotAndStartsAiJob() throws Exception {
        analyzerServer.expect(requestTo("http://analyzer.test/api/v1/analyze-repo"))
                .andExpect(method(POST))
                .andExpect(content().json("""
                        {"scope":"repository","target":"acme/shop","files":[
                          {"path":"src/App.java","language":"java","content":"class App {}"}
                        ]}
                        """))
                .andRespond(withSuccess(ANALYSIS, MediaType.APPLICATION_JSON));
        aiServiceServer.expect(requestTo("http://ai.test/generate"))
                .andExpect(method(POST))
                .andExpect(content().json(EXPECTED_AI_REQUEST))
                .andRespond(withStatus(HttpStatus.ACCEPTED).contentType(MediaType.APPLICATION_JSON)
                        .body("{\"id\":\"job-123\",\"status\":\"pending\"}"));

        JsonNode job = generationService.generate(USER_ID, REPOSITORY_ID,
                new DocumentationGenerationRequest("default", "en"));

        assertEquals("job-123", job.path("id").asText());
        assertEquals("pending", job.path("status").asText());
        analyzerServer.verify();
        aiServiceServer.verify();
    }

    @Test
    void reportsAnalyzerFailureWithoutStartingAiJob() {
        analyzerServer.expect(requestTo("http://analyzer.test/api/v1/analyze-repo"))
                .andRespond(withServerError());

        ApiException error = assertThrows(ApiException.class,
                () -> generationService.generate(USER_ID, REPOSITORY_ID, null));

        assertEquals("ANALYZER_FAILED", error.getCode());
        analyzerServer.verify();
        aiServiceServer.verify();
    }

    @Test
    void reportsAiServiceFailureAfterSuccessfulAnalysis() {
        analyzerServer.expect(requestTo("http://analyzer.test/api/v1/analyze-repo"))
                .andRespond(withSuccess(ANALYSIS, MediaType.APPLICATION_JSON));
        aiServiceServer.expect(requestTo("http://ai.test/generate"))
                .andExpect(content().json("""
                        {"scope":"repository","target":"acme/shop","files":[
                          {"path":"src/App.java","language":"java","status":"ok","classes":[],"functions":[],"endpoints":[]}
                        ]}
                        """))
                .andRespond(withServerError());

        ApiException error = assertThrows(ApiException.class,
                () -> generationService.generate(USER_ID, REPOSITORY_ID, null));

        assertEquals("AI_SERVICE_FAILED", error.getCode());
        analyzerServer.verify();
        aiServiceServer.verify();
    }

    @Test
    void mapsMissingUpstreamJobToNotFound() {
        analyzerServer.expect(requestTo("http://analyzer.test/api/v1/analyze-repo"))
                .andRespond(withSuccess(ANALYSIS, MediaType.APPLICATION_JSON));
        aiServiceServer.expect(requestTo("http://ai.test/generate"))
                .andRespond(withStatus(HttpStatus.ACCEPTED).contentType(MediaType.APPLICATION_JSON)
                        .body("{\"id\":\"job-missing\",\"status\":\"pending\"}"));
        aiServiceServer.expect(requestTo("http://ai.test/jobs/job-missing"))
                .andExpect(method(GET))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        generationService.generate(USER_ID, REPOSITORY_ID, null);
        ApiException error = assertThrows(ApiException.class,
                () -> generationService.getJob(USER_ID, "job-missing"));

        assertEquals(HttpStatus.NOT_FOUND, error.getStatus());
        assertEquals("NOT_FOUND", error.getCode());
        analyzerServer.verify();
        aiServiceServer.verify();
    }

    @Test
    void mapsResultNotReadyToConflict() {
        analyzerServer.expect(requestTo("http://analyzer.test/api/v1/analyze-repo"))
                .andRespond(withSuccess(ANALYSIS, MediaType.APPLICATION_JSON));
        aiServiceServer.expect(requestTo("http://ai.test/generate"))
                .andRespond(withStatus(HttpStatus.ACCEPTED).contentType(MediaType.APPLICATION_JSON)
                        .body("{\"id\":\"job-pending\",\"status\":\"pending\"}"));
        aiServiceServer.expect(requestTo("http://ai.test/jobs/job-pending/result"))
                .andExpect(method(GET))
                .andRespond(withStatus(HttpStatus.CONFLICT));

        generationService.generate(USER_ID, REPOSITORY_ID, null);
        ApiException error = assertThrows(ApiException.class,
                () -> generationService.getResult(USER_ID, "job-pending"));

        assertEquals(HttpStatus.CONFLICT, error.getStatus());
        assertEquals("DOCUMENTATION_NOT_READY", error.getCode());
        analyzerServer.verify();
        aiServiceServer.verify();
    }

    @Test
    void doesNotAllowAnotherUserToReadDocumentationJob() {
        analyzerServer.expect(requestTo("http://analyzer.test/api/v1/analyze-repo"))
                .andRespond(withSuccess(ANALYSIS, MediaType.APPLICATION_JSON));
        aiServiceServer.expect(requestTo("http://ai.test/generate"))
                .andRespond(withStatus(HttpStatus.ACCEPTED).contentType(MediaType.APPLICATION_JSON)
                        .body("{\"id\":\"job-owned\",\"status\":\"pending\"}"));

        generationService.generate(USER_ID, REPOSITORY_ID, null);
        ApiException error = assertThrows(ApiException.class,
                () -> generationService.getJob("different-user", "job-owned"));

        assertEquals(HttpStatus.FORBIDDEN, error.getStatus());
        aiServiceServer.verify();
    }

    @Test
    void rejectsSnapshotWithoutAnalyzableFilesBeforeCallingServices() {
        RepositorySnapshot emptySnapshot = new RepositorySnapshot(
                snapshot().repository(), "main", snapshot().headCommit(), Map.of(), List.of(), List.of(),
                new RepositorySnapshot.SyncStats(1, 0, 0, 1, false, false), List.of(), Instant.now());
        when(repositorySyncService.latest(USER_ID, REPOSITORY_ID)).thenReturn(emptySnapshot);

        ApiException error = assertThrows(ApiException.class,
                () -> generationService.generate(USER_ID, REPOSITORY_ID, null));

        assertEquals("BAD_REQUEST", error.getCode());
        analyzerServer.verify();
        aiServiceServer.verify();
    }

    private static RepositorySnapshot snapshot() {
        return new RepositorySnapshot(
                new RepositorySnapshot.RepositoryInfo(42L, "acme/shop", "acme", "shop", null,
                        false, false, "main", "https://github.com/acme/shop", "Java", 1L, null),
                "main",
                new RepositorySnapshot.CommitInfo("a".repeat(40), "init", null, null,
                        Instant.parse("2026-01-01T00:00:00Z"), "https://github.com/acme/shop/commit/init"),
                Map.of(),
                List.of(new RepositorySnapshot.SourceFile(
                        "src/App.java", "b".repeat(40), 12, "java", "class App {}", null)),
                List.of(),
                new RepositorySnapshot.SyncStats(1, 1, 1, 0, false, false),
                List.of(), Instant.now());
    }
}
