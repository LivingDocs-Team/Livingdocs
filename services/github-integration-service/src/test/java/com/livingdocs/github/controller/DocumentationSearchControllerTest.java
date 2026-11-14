package com.livingdocs.github.controller;

import com.livingdocs.github.dto.RepositoryResponse;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.exception.GlobalExceptionHandler;
import com.livingdocs.github.service.DocumentationSearchService;
import com.livingdocs.github.service.RepositoryManagementService;
import com.livingdocs.github.service.RepositorySyncService;
import com.livingdocs.github.sync.RepositorySnapshot;
import com.livingdocs.github.sync.RepositorySyncException;
import com.livingdocs.github.sync.SyncErrorCode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.client.RestClient;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.http.HttpMethod.POST;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class DocumentationSearchControllerTest {
    private static final String USER_ID = "user-1";
    private static final UUID REPOSITORY_ID = UUID.fromString("11111111-1111-1111-1111-111111111111");
    private static final UUID OTHER_REPOSITORY_ID = UUID.fromString("22222222-2222-2222-2222-222222222222");

    private RepositorySyncService syncService;
    private RepositoryManagementService repositoryService;
    private MockRestServiceServer analyzer;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        syncService = mock(RepositorySyncService.class);
        repositoryService = mock(RepositoryManagementService.class);
        RestClient.Builder clientBuilder = RestClient.builder().baseUrl("http://analyzer.test");
        analyzer = MockRestServiceServer.bindTo(clientBuilder).build();
        DocumentationSearchService service = new DocumentationSearchService(
                syncService, repositoryService, clientBuilder.build());
        mockMvc = MockMvcBuilders.standaloneSetup(new DocumentationSearchController(service))
                .setControllerAdvice(new GlobalExceptionHandler()).build();

        RepositoryResponse repository = new RepositoryResponse(REPOSITORY_ID, "ws-user-1", 42L,
                "acme/shop", "main", false, "https://github.com/acme/shop", "CONNECTED", null, Instant.EPOCH);
        RepositorySnapshot snapshot = new RepositorySnapshot(
                new RepositorySnapshot.RepositoryInfo(42L, "acme/shop", "acme", "shop", null,
                        false, false, "main", "https://github.com/acme/shop", "Java", 1L, null),
                "main", new RepositorySnapshot.CommitInfo("abc123", "test", "user", "user", Instant.EPOCH,
                        "https://github.com/acme/shop/commit/abc123"), Map.of(), List.of(), List.of(), null, List.of(), Instant.EPOCH);
        when(repositoryService.get(USER_ID, REPOSITORY_ID)).thenReturn(repository);
        when(syncService.latestOrSync(USER_ID, REPOSITORY_ID)).thenReturn(snapshot);
    }

    @Test
    void apiReturnsDocumentationAndCodeHitsWithScoringAndSourceMetadata() throws Exception {
        expectAnalysis("""
                {"files":[{"path":"src/Checkout.java","language":"java","classes":[
                  {"name":"CheckoutService","kind":"class","docstring":"Handles checkout requests.","lineno":8,"methods":[]}
                ],"functions":[],"endpoints":[]}]}
                """);

        mockMvc.perform(get("/api/repositories/{id}/documentation/search", REPOSITORY_ID)
                        .queryParam("q", " checkout ").header("X-User-Id", USER_ID))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.query").value("checkout"))
                .andExpect(jsonPath("$.total").value(2))
                .andExpect(jsonPath("$.results.length()").value(2))
                .andExpect(jsonPath("$.results[0].type").value("documentation"))
                .andExpect(jsonPath("$.results[0].title").value("CheckoutService"))
                .andExpect(jsonPath("$.results[0].summary").value("Handles checkout requests."))
                .andExpect(jsonPath("$.results[0].repositoryId").value(REPOSITORY_ID.toString()))
                .andExpect(jsonPath("$.results[0].repositoryName").value("acme/shop"))
                .andExpect(jsonPath("$.results[0].path").value("src/Checkout.java"))
                .andExpect(jsonPath("$.results[0].language").value("java"))
                .andExpect(jsonPath("$.results[0].line").value(8))
                .andExpect(jsonPath("$.results[0].score").isNumber())
                .andExpect(jsonPath("$.results[0].url").value(
                        "https://github.com/acme/shop/blob/main/src/Checkout.java#L8"))
                .andExpect(jsonPath("$.results[1].type").value("code"));
        analyzer.verify();
    }

    @Test
    void rejectsMissingIdentityQueryAndMalformedRepositoryId() throws Exception {
        mockMvc.perform(get("/api/repositories/{id}/documentation/search", REPOSITORY_ID)
                        .queryParam("q", "checkout"))
                .andExpect(status().isBadRequest());
        mockMvc.perform(get("/api/repositories/{id}/documentation/search", REPOSITORY_ID)
                        .header("X-User-Id", USER_ID))
                .andExpect(status().isBadRequest());
        mockMvc.perform(get("/api/repositories/not-a-uuid/documentation/search")
                        .queryParam("q", "checkout").header("X-User-Id", USER_ID))
                .andExpect(status().isBadRequest());
        verifyNoInteractions(syncService);
        analyzer.verify();
    }

    @Test
    void rejectsBlankQueryBeforeFetchingRepository() throws Exception {
        mockMvc.perform(get("/api/repositories/{id}/documentation/search", REPOSITORY_ID)
                        .queryParam("q", "  ").header("X-User-Id", USER_ID))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("BAD_REQUEST"));
        verifyNoInteractions(repositoryService, syncService);
        analyzer.verify();
    }

    @Test
    void enforcesRepositoryIsolationBeforeAnalyzerAccess() throws Exception {
        when(repositoryService.get(USER_ID, OTHER_REPOSITORY_ID))
                .thenThrow(ApiException.forbidden("Repository belongs to a different account."));
        mockMvc.perform(get("/api/repositories/{id}/documentation/search", OTHER_REPOSITORY_ID)
                        .queryParam("q", "checkout").header("X-User-Id", USER_ID))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("FORBIDDEN"));
        verifyNoInteractions(syncService);
        analyzer.verify();
    }

    @Test
    void returnsNotFoundWhenAWellFormedRepositoryIdDoesNotExist() throws Exception {
        when(repositoryService.get(USER_ID, OTHER_REPOSITORY_ID))
                .thenThrow(ApiException.notFound("Repository was not found."));
        mockMvc.perform(get("/api/repositories/{id}/documentation/search", OTHER_REPOSITORY_ID)
                        .queryParam("q", "checkout").header("X-User-Id", USER_ID))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("NOT_FOUND"));
        verifyNoInteractions(syncService);
        analyzer.verify();
    }

    @Test
    void reportsUnavailableRepositorySnapshotAndAnalyzerFailureAsApiErrors() throws Exception {
        when(syncService.latestOrSync(USER_ID, REPOSITORY_ID))
                .thenThrow(ApiException.notFound("No synchronized snapshot is available."));
        mockMvc.perform(get("/api/repositories/{id}/documentation/search", REPOSITORY_ID)
                        .queryParam("q", "checkout").header("X-User-Id", USER_ID))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("NOT_FOUND"));
        analyzer.verify();

        // Restore the snapshot and invoke the analyzer error path.
        doReturn(snapshot()).when(syncService).latestOrSync(USER_ID, REPOSITORY_ID);
        analyzer.expect(requestTo("http://analyzer.test/api/v1/analyze-repo"))
                .andExpect(method(POST)).andRespond(withServerError());
        mockMvc.perform(get("/api/repositories/{id}/documentation/search", REPOSITORY_ID)
                        .queryParam("q", "checkout").header("X-User-Id", USER_ID))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.code").value("ANALYZER_FAILED"));
        analyzer.verify();
    }

    @Test
    void mapsRepositorySynchronizationFailureToRetryableApiResponse() throws Exception {
        when(syncService.latestOrSync(USER_ID, REPOSITORY_ID))
                .thenThrow(new RepositorySyncException(SyncErrorCode.GITHUB_UNAVAILABLE,
                        "GitHub could not provide the latest repository snapshot."));
        mockMvc.perform(get("/api/repositories/{id}/documentation/search", REPOSITORY_ID)
                        .queryParam("q", "checkout").header("X-User-Id", USER_ID))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.code").value("GITHUB_UNAVAILABLE"));
        analyzer.verify();
    }

    @Test
    void returnsGatewayErrorWhenAnalyzerResponseHasNoFiles() throws Exception {
        analyzer.expect(requestTo("http://analyzer.test/api/v1/analyze-repo"))
                .andExpect(method(POST)).andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));
        mockMvc.perform(get("/api/repositories/{id}/documentation/search", REPOSITORY_ID)
                        .queryParam("q", "checkout").header("X-User-Id", USER_ID))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.code").value("ANALYZER_INVALID_RESPONSE"));
        analyzer.verify();
    }

    private void expectAnalysis(String response) {
        analyzer.expect(requestTo("http://analyzer.test/api/v1/analyze-repo"))
                .andExpect(method(POST)).andRespond(withSuccess(response, MediaType.APPLICATION_JSON));
    }

    private static RepositorySnapshot snapshot() {
        return new RepositorySnapshot(
                new RepositorySnapshot.RepositoryInfo(42L, "acme/shop", "acme", "shop", null,
                        false, false, "main", "https://github.com/acme/shop", "Java", 1L, null),
                "main", new RepositorySnapshot.CommitInfo("abc123", "test", "user", "user", Instant.EPOCH,
                        "https://github.com/acme/shop/commit/abc123"), Map.of(), List.of(), List.of(), null, List.of(), Instant.EPOCH);
    }
}



