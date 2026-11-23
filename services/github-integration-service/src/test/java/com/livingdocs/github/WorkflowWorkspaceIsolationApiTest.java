package com.livingdocs.github;

import com.livingdocs.github.entity.DocumentWorkflow;
import com.livingdocs.github.repository.DocumentWorkflowRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.util.UUID;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Workflows of a managed workspace are visible and decidable only to callers the BFF reports as members
 * ({@code WORKSPACE:<id>} in X-User-Authorities). Personal workspaces stay the shared review pool.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(com.livingdocs.github.security.InternalServiceTestMvcConfig.class)
class WorkflowWorkspaceIsolationApiTest {
    private static final String WS_A = "workspace-11111111-1111-1111-1111-111111111111";
    private static final String WS_B = "workspace-22222222-2222-2222-2222-222222222222";
    private static final String MANAGER = "ROLE_MANAGER,DOCUMENT_APPROVAL_QUEUE_VIEW,DOCUMENT_APPROVE,DOCUMENT_REJECT,DOCUMENT_VIEW";
    private static final String STAFF = "ROLE_STAFF,DOCUMENT_REVIEW_QUEUE_VIEW,DOCUMENT_REVIEW,DOCUMENT_CLAIM";

    @Autowired MockMvc mvc;
    @Autowired DocumentWorkflowRepository workflows;

    private UUID inA;
    private UUID inB;
    private UUID personal;

    @BeforeEach
    void setUp() {
        workflows.deleteAll();
        inA = pendingManager("doc-a", WS_A);
        inB = pendingManager("doc-b", WS_B);
        personal = pendingManager("doc-p", null);
    }

    private UUID pendingManager(String documentId, String workspace) {
        DocumentWorkflow workflow = new DocumentWorkflow(documentId, documentId, "owner-1");
        workflow.assignWorkspace(workspace);
        workflow.submit(1);
        workflow.claim("staff-1");
        workflow.review(com.livingdocs.github.entity.StaffReviewResult.PASSED, "ok");
        return workflows.saveAndFlush(workflow).getId();
    }

    private static String member(String base, String... workspaces) {
        StringBuilder value = new StringBuilder(base);
        for (String workspace : workspaces) value.append(",WORKSPACE:").append(workspace);
        return value.toString();
    }

    @Test
    void managerQueueListsOnlyWorkspacesTheCallerBelongsToAndThePersonalPool() throws Exception {
        mvc.perform(get("/api/document-workflows/manager/queue").header("X-User-Id", "m1")
                        .header("X-User-Authorities", member(MANAGER, WS_A)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content.length()").value(2))
                .andExpect(jsonPath("$.content[?(@.documentId=='doc-a')]").exists())
                .andExpect(jsonPath("$.content[?(@.documentId=='doc-p')]").exists())
                .andExpect(jsonPath("$.content[?(@.documentId=='doc-b')]").doesNotExist());

        mvc.perform(get("/api/document-workflows/manager/queue").header("X-User-Id", "m2")
                        .header("X-User-Authorities", MANAGER))
                .andExpect(jsonPath("$.content.length()").value(1))
                .andExpect(jsonPath("$.content[0].documentId").value("doc-p"));

        mvc.perform(get("/api/document-workflows/manager/queue").header("X-User-Id", "admin")
                        .header("X-User-Authorities", member(MANAGER, "*")))
                .andExpect(jsonPath("$.content.length()").value(3));
    }

    @Test
    void aWorkflowOfAnotherWorkspaceIsNotFoundByIdAndCannotBeDecided() throws Exception {
        String outsider = member(MANAGER, WS_A);
        mvc.perform(get("/api/document-workflows/" + inB).header("X-User-Id", "m1")
                        .header("X-User-Authorities", outsider))
                .andExpect(status().isNotFound());
        mvc.perform(post("/api/document-workflows/" + inB + "/approve").header("X-User-Id", "m1")
                        .header("X-User-Authorities", outsider)
                        .contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isNotFound());
        mvc.perform(post("/api/document-workflows/" + inB + "/reject").header("X-User-Id", "m1")
                        .header("X-User-Authorities", outsider)
                        .contentType(MediaType.APPLICATION_JSON).content("{\"comment\":\"no\"}"))
                .andExpect(status().isNotFound());
        mvc.perform(get("/api/document-workflows/" + inB + "/history").header("X-User-Id", "m1")
                        .header("X-User-Authorities", outsider))
                .andExpect(status().isNotFound());

        mvc.perform(get("/api/document-workflows/" + inA).header("X-User-Id", "m1")
                        .header("X-User-Authorities", outsider))
                .andExpect(status().isOk());
    }

    @Test
    void staffClaimAndQueueAreScopedToo() throws Exception {
        DocumentWorkflow pending = new DocumentWorkflow("doc-staff", "doc-staff", "owner-1");
        pending.assignWorkspace(WS_B);
        pending.submit(1);
        UUID staffWorkflow = workflows.saveAndFlush(pending).getId();

        mvc.perform(get("/api/document-workflows/staff/queue").header("X-User-Id", "s1")
                        .header("X-User-Authorities", member(STAFF, WS_A)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[?(@.documentId=='doc-staff')]").doesNotExist());
        mvc.perform(post("/api/document-workflows/" + staffWorkflow + "/claim").header("X-User-Id", "s1")
                        .header("X-User-Authorities", member(STAFF, WS_A))
                        .contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isNotFound());
        mvc.perform(post("/api/document-workflows/" + staffWorkflow + "/claim").header("X-User-Id", "s2")
                        .header("X-User-Authorities", member(STAFF, WS_B))
                        .contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isOk());
    }

    @Test
    void historyDiscoveryAndOversightRespectTheScope() throws Exception {
        mvc.perform(get("/api/document-workflows/history-accessible").header("X-User-Id", "m1")
                        .header("X-User-Authorities", member(MANAGER, WS_A)))
                .andExpect(jsonPath("$.content[?(@.documentId=='doc-b')]").doesNotExist())
                .andExpect(jsonPath("$.content[?(@.documentId=='doc-a')]").exists());

        String lead = "ROLE_TECHNICAL_LEAD,DOCUMENT_TECHNICAL_REVIEW";
        mvc.perform(get("/api/document-workflows/history-accessible").header("X-User-Id", "tl")
                        .header("X-User-Authorities", member(lead, WS_B)))
                .andExpect(jsonPath("$.content[?(@.documentId=='doc-b')]").exists())
                .andExpect(jsonPath("$.content[?(@.documentId=='doc-a')]").doesNotExist());
    }
}
