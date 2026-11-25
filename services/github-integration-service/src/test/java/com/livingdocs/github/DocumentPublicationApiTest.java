package com.livingdocs.github;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import com.livingdocs.github.entity.DocumentPublication;
import com.livingdocs.github.entity.DocumentWorkflow;
import com.livingdocs.github.repository.DocumentPublicationRepository;
import com.livingdocs.github.repository.DocumentWorkflowRepository;

/** The publication record: one per workflow and version, readable only by those who may read the workflow. */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(com.livingdocs.github.security.InternalServiceTestMvcConfig.class)
class DocumentPublicationApiTest {
    private static final String WS_A = "workspace-11111111-1111-1111-1111-111111111111";
    private static final String OWNER = "ROLE_DEVELOPER,DOCUMENT_VIEW";
    private static final String MANAGER = "ROLE_MANAGER,DOCUMENT_APPROVAL_QUEUE_VIEW,DOCUMENT_APPROVE";
    private static final String LEAD = "ROLE_TECHNICAL_LEAD,DOCUMENT_TECHNICAL_REVIEW";

    @Autowired MockMvc mvc;
    @Autowired DocumentWorkflowRepository workflows;
    @Autowired DocumentPublicationRepository publications;

    private UUID personal;
    private UUID managed;

    @BeforeEach
    void setUp() {
        publications.deleteAll();
        workflows.deleteAll();
        personal = approved("doc-p", null);
        managed = approved("doc-m", WS_A);
        publications.saveAndFlush(publication(personal, "doc-p", 2, "a".repeat(40)));
        publications.saveAndFlush(publication(personal, "doc-p", 3, "b".repeat(40)));
        publications.saveAndFlush(publication(managed, "doc-m", 1, "c".repeat(40)));
    }

    @AfterEach
    void cleanUp() {
        publications.deleteAll();
        workflows.deleteAll();
    }

    private UUID approved(String documentId, String workspace) {
        DocumentWorkflow workflow = new DocumentWorkflow(documentId, documentId, "owner-1");
        workflow.assignWorkspace(workspace);
        workflow.submit(1);
        workflow.claim("staff-1");
        workflow.review(com.livingdocs.github.entity.StaffReviewResult.PASSED, "ok");
        workflow.decide("manager-1", com.livingdocs.github.entity.ManagerDecision.APPROVED, null);
        return workflows.saveAndFlush(workflow).getId();
    }

    private static DocumentPublication publication(UUID workflowId, String documentId, int version, String sha) {
        return new DocumentPublication(workflowId, documentId, version, UUID.randomUUID(), "main",
                ".livingdocs/" + documentId + "-v" + version + ".md", sha, "manager-1");
    }

    @Test
    void theOwnerReadsThePublicationsOfTheirWorkflowNewestFirst() throws Exception {
        mvc.perform(get("/api/document-workflows/{id}/publications", personal).header("X-User-Id", "owner-1")
                        .header("X-User-Authorities", OWNER))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2))
                .andExpect(jsonPath("$[0].version").value(3))
                .andExpect(jsonPath("$[0].commitSha").value("b".repeat(40)))
                .andExpect(jsonPath("$[0].branch").value("main"))
                .andExpect(jsonPath("$[0].publishedBy").value("manager-1"));
    }

    @Test
    void aStrangerCannotReadThem() throws Exception {
        mvc.perform(get("/api/document-workflows/{id}/publications", personal).header("X-User-Id", "stranger")
                        .header("X-User-Authorities", OWNER))
                .andExpect(status().isNotFound());
    }

    @Test
    void aWorkflowWithoutPublicationsHasAnEmptyList() throws Exception {
        UUID none = approved("doc-n", null);
        mvc.perform(get("/api/document-workflows/{id}/publications", none).header("X-User-Id", "manager-1")
                        .header("X-User-Authorities", MANAGER))
                .andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(0));
    }

    @Test
    void publicationsOfAManagedWorkspaceAreHiddenFromOutsiders() throws Exception {
        mvc.perform(get("/api/document-workflows/{id}/publications", managed).header("X-User-Id", "manager-1")
                        .header("X-User-Authorities", MANAGER))
                .andExpect(status().isNotFound());
        mvc.perform(get("/api/document-workflows/{id}/publications", managed).header("X-User-Id", "manager-1")
                        .header("X-User-Authorities", MANAGER + ",WORKSPACE:" + WS_A))
                .andExpect(status().isOk()).andExpect(jsonPath("$[0].commitSha").value("c".repeat(40)));
        mvc.perform(get("/api/document-workflows/{id}/publications", managed).header("X-User-Id", "tl")
                        .header("X-User-Authorities", LEAD))
                .andExpect(status().isNotFound());
    }

    @Test
    void theSameWorkflowAndVersionCannotBePublishedTwice() {
        assertThatThrownBy(() -> publications.saveAndFlush(publication(personal, "doc-p", 2, "d".repeat(40))))
                .isInstanceOf(DataIntegrityViolationException.class);
        assertThat(publications.findByWorkflowIdOrderByVersionDesc(personal)).hasSize(2);
    }
}
