package com.livingdocs.github.change;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.http.HttpMethod.GET;
import static org.springframework.http.HttpMethod.POST;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

/** LD-127: gọi ai-service tìm tài liệu bị ảnh hưởng (LD-122), với ai-service giả. */
class AffectedDocumentsClientTest {

    private static final List<AffectedDocumentsClient.ChangedFile> FILES = List.of(
            new AffectedDocumentsClient.ChangedFile("src/Invoice.java", "src/Bill.java", "RENAMED", "java",
                    List.of(new AffectedDocumentsClient.ChangedEntity("METHOD", "Invoice.total", "MODIFIED"))));

    private MockRestServiceServer aiServer;
    private AffectedDocumentsClient client;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder();
        aiServer = MockRestServiceServer.bindTo(builder).build();
        client = new AffectedDocumentsClient(builder.baseUrl("http://ai.test").build());
    }

    @Test
    void sendsOnlyTheRepositorysDocuments_andReadsTheAffectedParts() {
        aiServer.expect(requestTo("http://ai.test/documents")).andExpect(method(GET))
                .andRespond(withSuccess("""
                        [{"id": "d1", "target": "acme/docs"}, {"id": "d2", "target": "other/repo"},
                         {"id": "d3", "target": "ACME/Docs"}]""", MediaType.APPLICATION_JSON));
        aiServer.expect(requestTo("http://ai.test/internal/affected-documents")).andExpect(method(POST))
                .andExpect(content().json("""
                        {"repository": "acme/docs", "document_ids": ["d1", "d3"],
                         "files": [{"path": "src/Invoice.java", "previous_path": "src/Bill.java", "change": "RENAMED",
                                    "language": "java",
                                    "entities": [{"kind": "METHOD", "name": "Invoice.total", "change": "MODIFIED"}]}]}""",
                        true))
                .andRespond(withSuccess("""
                        {"documents": [{"source": "document", "path": "src/Bill.java", "document_id": "d1",
                                        "title": "Docs", "version": 2, "documents_file": "src/Bill.java",
                                        "dependency": "direct",
                                        "reasons": ["documents changed file src/Invoice.java", "mentions `Invoice.total`"],
                                        "matches": [{"term": "total", "target": "Invoice.total", "line": 7,
                                                     "excerpt": "`total()` adds the lines.", "in_code": true,
                                                     "exact": false, "kind": "name"}],
                                        "findings": 0}],
                         "warnings": []}""", MediaType.APPLICATION_JSON));

        List<AffectedDocumentsClient.Affected> found = client.find("acme/docs", FILES);

        assertThat(found).containsExactly(new AffectedDocumentsClient.Affected("d1", "Docs", 2, "src/Bill.java",
                "src/Bill.java", "direct", List.of("documents changed file src/Invoice.java", "mentions `Invoice.total`"),
                List.of(new AffectedDocumentsClient.Match("Invoice.total", "name", 7, "`total()` adds the lines."))));
        aiServer.verify();
    }

    @Test
    void repositoryWithoutDocuments_isNotSentToTheAiService() {
        aiServer.expect(requestTo("http://ai.test/documents"))
                .andRespond(withSuccess("[{\"id\": \"d2\", \"target\": \"other/repo\"}]", MediaType.APPLICATION_JSON));

        assertThat(client.find("acme/docs", FILES)).isEmpty();
        aiServer.verify();  // không có POST nào
    }

    @Test
    void aiServiceError_isReportedAsUnavailable() {
        aiServer.expect(requestTo("http://ai.test/documents")).andRespond(withServerError());
        assertUnavailable();

        aiServer.reset();
        aiServer.expect(requestTo("http://ai.test/documents"))
                .andRespond(withSuccess("[{\"id\": \"d1\", \"target\": \"acme/docs\"}]", MediaType.APPLICATION_JSON));
        aiServer.expect(requestTo("http://ai.test/internal/affected-documents")).andRespond(withServerError());
        assertUnavailable();
    }

    private void assertUnavailable() {
        assertThatThrownBy(() -> client.find("acme/docs", FILES))
                .isInstanceOfSatisfying(SourceChangeException.class,
                        e -> assertThat(e.getCode()).isEqualTo("AI_SERVICE_UNAVAILABLE"));
    }
}
