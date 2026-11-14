
package com.livingdocs.github.controller;

import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Instant;
import java.util.Set;
import java.util.UUID;

import com.livingdocs.github.dto.WorkflowDtos.WorkflowResponse;
import com.livingdocs.github.entity.DocumentWorkflowStatus;
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
}



