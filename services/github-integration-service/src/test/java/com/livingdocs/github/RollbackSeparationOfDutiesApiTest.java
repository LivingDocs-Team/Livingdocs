package com.livingdocs.github;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import com.livingdocs.github.entity.DocumentWorkflow;
import com.livingdocs.github.entity.DocumentWorkflowAudit;
import com.livingdocs.github.entity.StaffReviewResult;
import com.livingdocs.github.repository.DocumentWorkflowAuditRepository;
import com.livingdocs.github.repository.DocumentWorkflowRepository;

/** Whoever requested a rollback cannot approve the restored version; another Manager can. */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(com.livingdocs.github.security.InternalServiceTestMvcConfig.class)
class RollbackSeparationOfDutiesApiTest {
    private static final String MANAGER = "ROLE_MANAGER,DOCUMENT_APPROVAL_QUEUE_VIEW,DOCUMENT_APPROVE,DOCUMENT_REJECT";

    @Autowired MockMvc mvc;
    @Autowired DocumentWorkflowRepository workflows;
    @Autowired DocumentWorkflowAuditRepository audit;
    @Autowired JdbcTemplate jdbc;

    private UUID workflowId;

    @BeforeEach
    void setUp() {
        jdbc.update("DELETE FROM approval_delegations");
        audit.deleteAll();
        workflows.deleteAll();
        DocumentWorkflow workflow = new DocumentWorkflow("doc-rb", "Rollback", "owner-1");
        workflow.submit(3);
        workflow.claim("staff-1");
        workflow.review(StaffReviewResult.PASSED, "ok");
        workflowId = workflows.saveAndFlush(workflow).getId();
        DocumentWorkflowAudit requested = new DocumentWorkflowAudit(workflowId, "m1", "ROLLBACK_REQUESTED",
                "APPROVED", "PENDING_STAFF_REVIEW", "Restored from version 1");
        requested.setDocumentVersion(3);
        audit.saveAndFlush(requested);
    }

    @AfterEach
    void cleanUp() {
        audit.deleteAll();
        workflows.deleteAll();
    }

    private int approveAs(String manager) throws Exception {
        return mvc.perform(post("/api/document-workflows/" + workflowId + "/approve").header("X-User-Id", manager)
                        .header("X-User-Authorities", MANAGER).contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andReturn().getResponse().getStatus();
    }

    @Test
    void theManagerWhoRequestedTheRollbackCannotApproveIt() throws Exception {
        mvc.perform(post("/api/document-workflows/" + workflowId + "/approve").header("X-User-Id", "m1")
                        .header("X-User-Authorities", MANAGER).contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void anotherManagerIsNotBlockedByTheRule() throws Exception {
        // the document service is not reachable in this test, so the decision itself fails later and differently
        assertThat(approveAs("m2")).isNotEqualTo(403);
    }

    @Test
    void theRequesterMayStillRejectTheirOwnRequest() throws Exception {
        int status = mvc.perform(post("/api/document-workflows/" + workflowId + "/reject").header("X-User-Id", "m1")
                        .header("X-User-Authorities", MANAGER).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"comment\":\"Withdrawn\"}"))
                .andReturn().getResponse().getStatus();
        assertThat(status).isNotEqualTo(403);
    }

    @Test
    void theStaffReviewerStillCannotMakeTheFinalDecision() throws Exception {
        mvc.perform(post("/api/document-workflows/" + workflowId + "/approve").header("X-User-Id", "staff-1")
                        .header("X-User-Authorities", MANAGER).contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isForbidden());
    }
}
