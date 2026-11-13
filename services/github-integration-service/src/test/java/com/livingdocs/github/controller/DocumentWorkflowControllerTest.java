
package com.livingdocs.github.controller;

import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Instant;
import java.util.List;
import java.util.Set;
import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.dto.WorkflowDtos.AuditResponse;
import com.livingdocs.github.dto.WorkflowDtos.PageResponse;
import com.livingdocs.github.dto.WorkflowDtos.StaffReviewRequest;
import com.livingdocs.github.dto.WorkflowDtos.WorkflowResponse;
import com.livingdocs.github.entity.DocumentWorkflowStatus;
import com.livingdocs.github.entity.ManagerDecision;
import com.livingdocs.github.entity.StaffReviewResult;
import com.livingdocs.github.service.DocumentWorkflowService;
import com.livingdocs.github.service.DocumentationGenerationService;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

class DocumentWorkflowControllerTest {

    private static final UUID WORKFLOW_ID =
            UUID.fromString("123e4567-e89b-12d3-a456-426614174000");
    private static final String STAFF_ID = "staff-1";
    private static final String MANAGER_ID = "manager-1";
    private static final Set<String> STAFF_AUTHORITIES =
            Set.of("ROLE_STAFF", "DOCUMENT_CLAIM", "DOCUMENT_RELEASE", "DOCUMENT_REVIEW");
    private static final Set<String> MANAGER_AUTHORITIES =
            Set.of("ROLE_MANAGER", "DOCUMENT_APPROVAL_QUEUE_VIEW", "DOCUMENT_APPROVE", "DOCUMENT_REJECT");

    private DocumentWorkflowService workflowService;
    private DocumentationGenerationService documentService;
    private MockMvc mockMvc;
    private LocalValidatorFactoryBean validator;

    @BeforeEach
    void setUp() {
        workflowService = mock(DocumentWorkflowService.class);
        documentService = mock(DocumentationGenerationService.class);

        validator = new LocalValidatorFactoryBean();
        validator.afterPropertiesSet();

        mockMvc = MockMvcBuilders
                .standaloneSetup(
                        new DocumentWorkflowController(
                                workflowService,
                                documentService
                        )
                )
                .setValidator(validator)
                .build();
    }

    @Test
    void managerCanRequestDocumentRollback() throws Exception {
        WorkflowResponse response = new WorkflowResponse(
                WORKFLOW_ID,
                "doc-1",
                "Test document",
                "owner-1",
                DocumentWorkflowStatus.PENDING_STAFF_REVIEW,
                3,
                null,
                null,
                null,
                null,
                null,
                null,
                Instant.now(),
                Instant.now(),
                Instant.now(),
                null,
                null,
                1L
        );

        when(workflowService.rollback(
                "manager-1",
                Set.of("ROLE_MANAGER", "DOCUMENT_ROLLBACK"),
                WORKFLOW_ID,
                1,
                "Restore stable version"
        )).thenReturn(response);

        mockMvc.perform(post(
                        "/api/document-workflows/{id}/rollback",
                        WORKFLOW_ID
                )
                .header("X-User-Id", "manager-1")
                .header(
                        "X-User-Authorities",
                        "ROLE_MANAGER,DOCUMENT_ROLLBACK"
                )
                .contentType("application/json")
                .content("""
                        {
                            "sourceVersion": 1,
                            "reason": "Restore stable version"
                        }
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.documentId").value("doc-1"))
                .andExpect(jsonPath("$.status")
                        .value("PENDING_STAFF_REVIEW"))
                .andExpect(jsonPath("$.submittedDocumentVersion")
                        .value(3));

        verify(workflowService).rollback(
                "manager-1",
                Set.of("ROLE_MANAGER", "DOCUMENT_ROLLBACK"),
                WORKFLOW_ID,
                1,
                "Restore stable version"
        );
    }

    @Test
    void rollbackRejectsInvalidSourceVersion() throws Exception {
        mockMvc.perform(post(
                        "/api/document-workflows/{id}/rollback",
                        WORKFLOW_ID
                )
                .header("X-User-Id", "manager-1")
                .header(
                        "X-User-Authorities",
                        "ROLE_MANAGER,DOCUMENT_ROLLBACK"
                )
                .contentType("application/json")
                .content("""
                        {
                            "sourceVersion": 0,
                            "reason": "Restore stable version"
                        }
                        """))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(workflowService);
    }

    @Test
    void staffAndManagerQueuesForwardPaginationAndIdentity() throws Exception {
        PageResponse<WorkflowResponse> page = new PageResponse<>(List.of(), 2, 10, 0, 0, true, true);
        when(workflowService.staffQueue(STAFF_ID, STAFF_AUTHORITIES, 2, 10)).thenReturn(page);
        when(workflowService.managerQueue(MANAGER_AUTHORITIES, 1, 5)).thenReturn(page);
        when(workflowService.historyAccessible(MANAGER_ID, MANAGER_AUTHORITIES, 3, 7)).thenReturn(page);

        mockMvc.perform(get("/api/document-workflows/staff/queue")
                        .header("X-User-Id", STAFF_ID)
                        .header("X-User-Authorities", "ROLE_STAFF,DOCUMENT_CLAIM,DOCUMENT_RELEASE,DOCUMENT_REVIEW")
                        .param("page", "2").param("size", "10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page").value(2))
                .andExpect(jsonPath("$.size").value(10));
        mockMvc.perform(get("/api/document-workflows/manager/queue")
                        .header("X-User-Id", MANAGER_ID)
                        .header("X-User-Authorities", "ROLE_MANAGER,DOCUMENT_APPROVAL_QUEUE_VIEW,DOCUMENT_APPROVE,DOCUMENT_REJECT")
                        .param("page", "1").param("size", "5"))
                .andExpect(status().isOk());
        mockMvc.perform(get("/api/document-workflows/history-accessible")
                        .header("X-User-Id", MANAGER_ID)
                        .header("X-User-Authorities", "ROLE_MANAGER,DOCUMENT_APPROVAL_QUEUE_VIEW,DOCUMENT_APPROVE,DOCUMENT_REJECT")
                        .param("page", "3").param("size", "7"))
                .andExpect(status().isOk());

        verify(workflowService).staffQueue(STAFF_ID, STAFF_AUTHORITIES, 2, 10);
        verify(workflowService).managerQueue(MANAGER_AUTHORITIES, 1, 5);
        verify(workflowService).historyAccessible(MANAGER_ID, MANAGER_AUTHORITIES, 3, 7);
    }

    @Test
    void claimReleaseAndStaffReviewMapToTheirWorkflowRequests() throws Exception {
        mockMvc.perform(post("/api/document-workflows/{id}/claim", WORKFLOW_ID)
                        .header("X-User-Id", STAFF_ID)
                        .header("X-User-Authorities", "ROLE_STAFF,DOCUMENT_CLAIM,DOCUMENT_RELEASE,DOCUMENT_REVIEW"))
                .andExpect(status().isOk());
        mockMvc.perform(post("/api/document-workflows/{id}/release", WORKFLOW_ID)
                        .header("X-User-Id", STAFF_ID)
                        .header("X-User-Authorities", "ROLE_STAFF,DOCUMENT_CLAIM,DOCUMENT_RELEASE,DOCUMENT_REVIEW"))
                .andExpect(status().isOk());
        mockMvc.perform(post("/api/document-workflows/{id}/staff-review", WORKFLOW_ID)
                        .header("X-User-Id", STAFF_ID)
                        .header("X-User-Authorities", "ROLE_STAFF,DOCUMENT_CLAIM,DOCUMENT_RELEASE,DOCUMENT_REVIEW")
                        .contentType("application/json")
                        .content("{\"result\":\"CHANGES_REQUESTED\",\"comment\":\"Update the endpoint example.\"}"))
                .andExpect(status().isOk());

        verify(workflowService).claim(STAFF_ID, STAFF_AUTHORITIES, WORKFLOW_ID);
        verify(workflowService).release(STAFF_ID, STAFF_AUTHORITIES, WORKFLOW_ID);
        verify(workflowService).staffReview(STAFF_ID, STAFF_AUTHORITIES, WORKFLOW_ID,
                new StaffReviewRequest(StaffReviewResult.CHANGES_REQUESTED, "Update the endpoint example."));
    }

    @Test
    void approveSendsNoCommentAndRejectForwardsComment() throws Exception {
        mockMvc.perform(post("/api/document-workflows/{id}/approve", WORKFLOW_ID)
                        .header("X-User-Id", MANAGER_ID)
                        .header("X-User-Authorities", "ROLE_MANAGER,DOCUMENT_APPROVAL_QUEUE_VIEW,DOCUMENT_APPROVE,DOCUMENT_REJECT"))
                .andExpect(status().isOk());
        mockMvc.perform(post("/api/document-workflows/{id}/reject", WORKFLOW_ID)
                        .header("X-User-Id", MANAGER_ID)
                        .header("X-User-Authorities", "ROLE_MANAGER,DOCUMENT_APPROVAL_QUEUE_VIEW,DOCUMENT_APPROVE,DOCUMENT_REJECT")
                        .contentType("application/json")
                        .content("{\"comment\":\"The source links need correction.\"}"))
                .andExpect(status().isOk());

        verify(workflowService).decide(MANAGER_ID, MANAGER_AUTHORITIES, WORKFLOW_ID, ManagerDecision.APPROVED, null);
        verify(workflowService).decide(MANAGER_ID, MANAGER_AUTHORITIES, WORKFLOW_ID, ManagerDecision.REJECTED,
                "The source links need correction.");
    }

    @Test
    void evidenceComparisonAndAuditUseTheWorkflowEndpoints() throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        when(workflowService.evidence(MANAGER_ID, MANAGER_AUTHORITIES, WORKFLOW_ID))
                .thenReturn(mapper.readTree("{\"files\":[]}"));
        when(workflowService.reviewEvidence(STAFF_ID, STAFF_AUTHORITIES, WORKFLOW_ID))
                .thenReturn(mapper.readTree("{\"files\":[]}"));
        when(workflowService.reviewComparison(STAFF_ID, STAFF_AUTHORITIES, WORKFLOW_ID))
                .thenReturn(mapper.readTree("{\"pending_version\":{\"number\":2}}"));
        when(workflowService.history(MANAGER_ID, MANAGER_AUTHORITIES, WORKFLOW_ID)).thenReturn(List.of(
                new AuditResponse(UUID.randomUUID(), MANAGER_ID, "MANAGER", "REJECTED",
                        "PENDING_MANAGER_APPROVAL", "REJECTED", null, null, "Needs fixes", Instant.now())));

        mockMvc.perform(get("/api/document-workflows/{id}/evidence", WORKFLOW_ID)
                        .header("X-User-Id", MANAGER_ID)
                        .header("X-User-Authorities", "ROLE_MANAGER,DOCUMENT_APPROVAL_QUEUE_VIEW,DOCUMENT_APPROVE,DOCUMENT_REJECT"))
                .andExpect(status().isOk()).andExpect(content().json("{\"files\":[]}"));
        mockMvc.perform(get("/api/document-workflows/{id}/review-evidence", WORKFLOW_ID)
                        .header("X-User-Id", STAFF_ID)
                        .header("X-User-Authorities", "ROLE_STAFF,DOCUMENT_CLAIM,DOCUMENT_RELEASE,DOCUMENT_REVIEW"))
                .andExpect(status().isOk()).andExpect(content().json("{\"files\":[]}"));
        mockMvc.perform(get("/api/document-workflows/{id}/review-comparison", WORKFLOW_ID)
                        .header("X-User-Id", STAFF_ID)
                        .header("X-User-Authorities", "ROLE_STAFF,DOCUMENT_CLAIM,DOCUMENT_RELEASE,DOCUMENT_REVIEW"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.pending_version.number").value(2));
        mockMvc.perform(get("/api/document-workflows/{id}/history", WORKFLOW_ID)
                        .header("X-User-Id", MANAGER_ID)
                        .header("X-User-Authorities", "ROLE_MANAGER,DOCUMENT_APPROVAL_QUEUE_VIEW,DOCUMENT_APPROVE,DOCUMENT_REJECT"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].action").value("REJECTED"))
                .andExpect(jsonPath("$[0].comment").value("Needs fixes"));

        verify(workflowService).evidence(MANAGER_ID, MANAGER_AUTHORITIES, WORKFLOW_ID);
        verify(workflowService).reviewEvidence(STAFF_ID, STAFF_AUTHORITIES, WORKFLOW_ID);
        verify(workflowService).reviewComparison(STAFF_ID, STAFF_AUTHORITIES, WORKFLOW_ID);
        verify(workflowService).history(MANAGER_ID, MANAGER_AUTHORITIES, WORKFLOW_ID);
    }
}
