package com.livingdocs.github;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import com.livingdocs.github.dto.WorkflowDtos.PageResponse;
import com.livingdocs.github.service.DocumentWorkflowService;
import com.livingdocs.github.service.DocumentationGenerationService;

/**
 * LD-403: unauthenticated access to every document-workflow endpoint, through the real servlet
 * filter chain (InternalServiceAuthenticationFilter). Unlike the other MockMvc tests this one does
 * NOT install the default service credential, so each request reaches the filter as sent.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class DocumentWorkflowAuthenticationTest {

    private static final String VALID_CREDENTIAL = "Bearer test-only-internal-credential";
    private static final String ID = "123e4567-e89b-12d3-a456-426614174000";
    private static final String JSON_BODY = "{\"result\":\"PASSED\"}";

    /** Every endpoint of DocumentWorkflowController (method, path). */
    private static final List<String[]> WORKFLOW_ENDPOINTS = List.of(
            new String[] {"POST", "/api/documentation/jobs/job-1/document"},
            new String[] {"POST", "/api/document-workflows"},
            new String[] {"GET", "/api/document-workflows/mine"},
            new String[] {"GET", "/api/document-workflows/staff/queue"},
            new String[] {"GET", "/api/document-workflows/manager/queue"},
            new String[] {"GET", "/api/document-workflows/history-accessible"},
            new String[] {"GET", "/api/document-workflows/" + ID},
            new String[] {"GET", "/api/document-workflows/" + ID + "/document"},
            new String[] {"GET", "/api/document-workflows/" + ID + "/evidence"},
            new String[] {"GET", "/api/document-workflows/" + ID + "/review-evidence"},
            new String[] {"GET", "/api/document-workflows/" + ID + "/review-comparison"},
            new String[] {"GET", "/api/document-workflows/" + ID + "/history"},
            new String[] {"POST", "/api/document-workflows/" + ID + "/submit"},
            new String[] {"POST", "/api/document-workflows/" + ID + "/claim"},
            new String[] {"POST", "/api/document-workflows/" + ID + "/release"},
            new String[] {"POST", "/api/document-workflows/" + ID + "/reassign"},
            new String[] {"POST", "/api/document-workflows/" + ID + "/staff-review"},
            new String[] {"PUT", "/api/document-workflows/" + ID + "/document"},
            new String[] {"POST", "/api/document-workflows/" + ID + "/approve"},
            new String[] {"POST", "/api/document-workflows/" + ID + "/reject"},
            new String[] {"POST", "/api/document-workflows/" + ID + "/rollback"});

    @Autowired
    MockMvc mvc;

    @MockitoBean
    DocumentWorkflowService workflowService;
    @MockitoBean
    DocumentationGenerationService documentService;

    @Test
    void everyWorkflowEndpointRejectsRequestsWithoutTheServiceCredential() throws Exception {
        for (String[] endpoint : WORKFLOW_ENDPOINTS) {
            mvc.perform(call(endpoint))
                    .andExpect(status().isUnauthorized())
                    .andExpect(content().string(org.hamcrest.Matchers.containsString(
                            "INTERNAL_SERVICE_AUTH_REQUIRED")));
        }
        verifyNoInteractions(workflowService, documentService);
    }

    @Test
    void forgedIdentityHeadersDoNotReplaceTheServiceCredential() throws Exception {
        for (String[] endpoint : WORKFLOW_ENDPOINTS) {
            // A browser (or an attacker) that reaches the service directly can forge both headers.
            mvc.perform(call(endpoint)
                            .header("X-User-Id", "92")
                            .header("X-User-Authorities", "ROLE_MANAGER,DOCUMENT_APPROVE,DOCUMENT_REJECT"))
                    .andExpect(status().isUnauthorized());
        }
        verifyNoInteractions(workflowService, documentService);
    }

    @Test
    void wrongOrMalformedCredentialsAreRejected() throws Exception {
        for (String authorization : List.of("Bearer wrong-credential", "Basic dGVzdDp0ZXN0",
                "test-only-internal-credential", "Bearer ")) {
            mvc.perform(call(new String[] {"POST", "/api/document-workflows/" + ID + "/approve"})
                            .header("Authorization", authorization)
                            .header("X-User-Id", "92")
                            .header("X-User-Authorities", "ROLE_MANAGER,DOCUMENT_APPROVE"))
                    .andExpect(status().isUnauthorized());
        }
        verifyNoInteractions(workflowService);
    }

    @Test
    void validCredentialReachesTheControllerAndForwardsTheIdentityHeaders() throws Exception {
        when(workflowService.staffQueue(eq("42"), any(), anyInt(), anyInt()))
                .thenReturn(new PageResponse<>(List.of(), 0, 20, 0, 0, true, true));

        mvc.perform(request(HttpMethod.GET, "/api/document-workflows/staff/queue")
                        .header("Authorization", VALID_CREDENTIAL)
                        .header("X-User-Id", "42")
                        .header("X-User-Authorities", "ROLE_STAFF,DOCUMENT_REVIEW_QUEUE_VIEW"))
                .andExpect(status().isOk());

        verify(workflowService).staffQueue(eq("42"),
                eq(Set.of("ROLE_STAFF", "DOCUMENT_REVIEW_QUEUE_VIEW")), eq(0), eq(20));
    }

    @Test
    void validCredentialWithoutAnIdentityHeaderIsNotServed() throws Exception {
        mvc.perform(request(HttpMethod.GET, "/api/document-workflows/staff/queue")
                        .header("Authorization", VALID_CREDENTIAL))
                .andExpect(status().is4xxClientError());
        verifyNoInteractions(workflowService);
    }

    private static MockHttpServletRequestBuilder call(String[] endpoint) {
        MockHttpServletRequestBuilder builder = request(HttpMethod.valueOf(endpoint[0]), endpoint[1]);
        if (!"GET".equals(endpoint[0])) {
            builder.contentType(MediaType.APPLICATION_JSON).content(JSON_BODY);
        }
        return builder;
    }
}
