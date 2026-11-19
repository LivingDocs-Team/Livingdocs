package com.livingdocs.github.service;

import com.livingdocs.github.dto.DocumentationSearchResponse;
import com.livingdocs.github.dto.RepositoryResponse;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.sync.RepositorySnapshot;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.http.HttpMethod.POST;
import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verifyNoInteractions;

class DocumentationSearchServiceTest {
    private static final UUID REPOSITORY_ID = UUID.fromString("11111111-1111-1111-1111-111111111111");
    private RepositorySyncService syncService;
    private RepositoryManagementService repositoryService;
    private MockRestServiceServer server;
    private DocumentationSearchService service;

    @BeforeEach
    void setUp() {
        syncService = mock(RepositorySyncService.class);
        repositoryService = mock(RepositoryManagementService.class);
        RestClient.Builder builder = RestClient.builder().baseUrl("http://analyzer.test");
        server = MockRestServiceServer.bindTo(builder).build();
        service = new DocumentationSearchService(syncService, repositoryService, builder.build());
        RepositoryResponse repository = new RepositoryResponse(REPOSITORY_ID, "ws-user-1", 42L,
                "acme/shop", "main", false, "https://github.com/acme/shop", "CONNECTED", null, Instant.EPOCH);
        RepositorySnapshot snapshot = new RepositorySnapshot(
                new RepositorySnapshot.RepositoryInfo(42L, "acme/shop", "acme", "shop", null,
                        false, false, "main", "https://github.com/acme/shop", "Java", 1L, null),
                "main", new RepositorySnapshot.CommitInfo("abc123", "test", "user", "user", Instant.EPOCH,
                        "https://github.com/acme/shop/commit/abc123"), Map.of(), List.of(), List.of(), null, List.of(), Instant.EPOCH);
        when(repositoryService.get("user-1", REPOSITORY_ID)).thenReturn(repository);
        when(syncService.latestOrSync("user-1", REPOSITORY_ID)).thenReturn(snapshot);
    }

    @Test
    void findsDocumentationAndLinkedCodeEntityWithSourceNavigation() {
        server.expect(requestTo("http://analyzer.test/api/v1/analyze-repo")).andExpect(method(POST))
                .andRespond(withSuccess("""
                        {"files":[{"path":"src/Checkout.java","language":"java","classes":[
                          {"name":"CheckoutService","kind":"class","docstring":"Handles checkout requests.","lineno":8,"methods":[]}
                        ],"functions":[],"endpoints":[]}]}
                        """, APPLICATION_JSON));

        DocumentationSearchResponse response = service.search("user-1", REPOSITORY_ID, "checkout");
        assertEquals(2, response.total());
        assertEquals(List.of("documentation", "code"), response.results().stream().map(r -> r.type()).toList());
        assertEquals("https://github.com/acme/shop/blob/main/src/Checkout.java#L8", response.results().get(0).url());
        server.verify();
    }

    @Test
    void rejectsEmptyAndOversizedQueries() {
        assertThrows(ApiException.class, () -> service.search("user-1", REPOSITORY_ID, "  "));
        assertThrows(ApiException.class, () -> service.search("user-1", REPOSITORY_ID, "x".repeat(201)));
    }

    @Test
    void returnsAnEmptyResultSetWhenNothingMatches() {
        server.expect(requestTo("http://analyzer.test/api/v1/analyze-repo")).andExpect(method(POST))
                .andRespond(withSuccess("""
                        {"files":[{"path":"src/Checkout.java","language":"java","classes":[
                          {"name":"CheckoutService","kind":"class","docstring":"Handles checkout requests.","lineno":8,"methods":[]}
                        ],"functions":[],"endpoints":[]}]}
                        """, APPLICATION_JSON));
        DocumentationSearchResponse response = service.search("user-1", REPOSITORY_ID, "payment");
        assertEquals(0, response.total());
        assertEquals(List.of(), response.results());
        server.verify();
    }

    @Test
    void searchesFunctionAndMethodCodeEntitiesWithoutDocumentation() {
        server.expect(requestTo("http://analyzer.test/api/v1/analyze-repo")).andExpect(method(POST))
                .andRespond(withSuccess("""
                        {"files":[{"path":"src/Payments.java","language":"java","classes":[
                          {"name":"PaymentService","kind":"class","lineno":2,"methods":[
                            {"name":"processPayment","signature":"processPayment(Payment payment)","lineno":9}
                          ]}
                        ],"functions":[
                          {"name":"completePayment","signature":"completePayment()","lineno":30}
                        ],"endpoints":[]}]}
                        """, APPLICATION_JSON));

        DocumentationSearchResponse response = service.search("user-1", REPOSITORY_ID, "processPayment");
        assertEquals(1, response.total());
        assertEquals("code", response.results().get(0).type());
        assertEquals("PaymentService.processPayment", response.results().get(0).title());
        assertEquals(9, response.results().get(0).line());
        assertEquals("processPayment(Payment payment)", response.results().get(0).summary().substring("method - ".length()));
        server.verify();
    }

    @Test
    void ranksExactPhraseMatchesAheadOfPartialTokenMatches() {
        server.expect(requestTo("http://analyzer.test/api/v1/analyze-repo")).andExpect(method(POST))
                .andRespond(withSuccess("""
                        {"files":[{"path":"src/Payments.java","language":"java","classes":[
                          {"name":"AlphaBetaService","docstring":"alpha beta workflow","lineno":2,"methods":[]},
                          {"name":"AlphaWorker","docstring":"supports beta operations","lineno":20,"methods":[]}
                        ],"functions":[],"endpoints":[]}]}
                        """, APPLICATION_JSON));

        DocumentationSearchResponse response = service.search("user-1", REPOSITORY_ID, "alpha beta");
        List<DocumentationSearchResponse.SearchResult> docs = response.results().stream()
                .filter(hit -> hit.type().equals("documentation")).toList();
        assertEquals("AlphaBetaService", docs.get(0).title());
        assertEquals(110, docs.get(0).score());
        org.junit.jupiter.api.Assertions.assertTrue(docs.get(0).score() > docs.get(1).score());
        server.verify();
    }

    @Test
    void rejectsQueriesContainingControlCharacters() {
        assertThrows(ApiException.class, () -> service.search("user-1", REPOSITORY_ID, "checkout\nsecret"));
    }

    @Test
    void stopsBeforeSnapshotOrAnalyzerWhenRepositoryIsNotOwned() {
        UUID otherRepositoryId = UUID.fromString("22222222-2222-2222-2222-222222222222");
        when(repositoryService.get("user-1", otherRepositoryId))
                .thenThrow(ApiException.forbidden("Repository belongs to another user."));
        assertThrows(ApiException.class, () -> service.search("user-1", otherRepositoryId, "checkout"));
        verifyNoInteractions(syncService);
        server.verify();
    }

    @Test
    void surfacesMissingSnapshotAsAnApiFailure() {
        when(syncService.latestOrSync("user-1", REPOSITORY_ID))
                .thenThrow(ApiException.notFound("No synchronized snapshot exists."));
        assertThrows(ApiException.class, () -> service.search("user-1", REPOSITORY_ID, "checkout"));
        server.verify();
    }

    @Test
    void encodesSourcePathSpacesAndPreservesSlashInBranchLinks() {
        RepositoryResponse repository = new RepositoryResponse(REPOSITORY_ID, "ws-user-1", 42L,
                "acme/shop", "release/candidate", false, "https://github.com/acme/shop", "CONNECTED", null,
                Instant.EPOCH);
        when(repositoryService.get("user-1", REPOSITORY_ID)).thenReturn(repository);
        server.expect(requestTo("http://analyzer.test/api/v1/analyze-repo")).andExpect(method(POST))
                .andRespond(withSuccess("""
                        {"files":[{"path":"docs/Checkout Guide.md","language":"markdown","classes":[
                          {"name":"CheckoutGuide","kind":"class","docstring":"Checkout instructions.","lineno":7,"methods":[]}
                        ],"functions":[],"endpoints":[]}]}
                        """, APPLICATION_JSON));

        DocumentationSearchResponse response = service.search("user-1", REPOSITORY_ID, "checkout");
        assertEquals("https://github.com/acme/shop/blob/release/candidate/docs/Checkout%20Guide.md#L7",
                response.results().get(0).url());
        server.verify();
    }
}
