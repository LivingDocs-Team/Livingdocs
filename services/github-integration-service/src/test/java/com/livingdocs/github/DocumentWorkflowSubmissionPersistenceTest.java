package com.livingdocs.github;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Set;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.livingdocs.github.dto.WorkflowDtos.StaffReviewRequest;
import com.livingdocs.github.entity.DocumentWorkflow;
import com.livingdocs.github.entity.DocumentWorkflowAudit;
import com.livingdocs.github.entity.DocumentWorkflowStatus;
import com.livingdocs.github.entity.StaffReviewResult;
import com.livingdocs.github.repository.DocumentWorkflowAuditRepository;
import com.livingdocs.github.repository.DocumentWorkflowRepository;
import com.livingdocs.github.security.TokenEncryptor;
import com.livingdocs.github.service.DocumentWorkflowService;
import com.livingdocs.github.service.DocumentationGenerationService;

import jakarta.persistence.EntityManager;

/**
 * LD-402: workflow submission persistence, tested separately from the AI-service documents.
 *
 * <p>Every check reads the workflow back after {@code flush()} + {@code clear()}, so it sees what
 * is stored in the database (what a restarted service would load), not the entity in memory.
 * The real Flyway migrations create the schema.
 */
@DataJpaTest(properties = "spring.flyway.enabled=true")
@ActiveProfiles("test")
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(DocumentWorkflowSubmissionPersistenceTest.TestTokenEncryptorConfiguration.class)
class DocumentWorkflowSubmissionPersistenceTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class TestTokenEncryptorConfiguration {
        @Bean
        TokenEncryptor testTokenEncryptor(@Value("${security.token-encryption-key}") String testKey) {
            return new TokenEncryptor(testKey);
        }
    }

    private static final String OWNER = "73";
    private static final String STAFF = "81";
    private static final String DOCUMENT_ID = "ld402-doc";
    private static final Set<String> OWNER_AUTHORITIES = Set.of("ROLE_DEVELOPER", "DOCUMENT_CREATE",
            "DOCUMENT_SUBMIT", "DOCUMENT_VIEW", "DOCUMENT_UPDATE");
    private static final Set<String> STAFF_AUTHORITIES = Set.of("ROLE_STAFF", "DOCUMENT_CLAIM",
            "DOCUMENT_REVIEW");
    private static final ObjectMapper JSON = new ObjectMapper();

    @Autowired
    private DocumentWorkflowRepository workflows;

    @Autowired
    private DocumentWorkflowAuditRepository audit;

    @Autowired
    private EntityManager entityManager;

    private DocumentationGenerationService documents;
    private DocumentWorkflowService service;

    @BeforeEach
    void setUp() {
        documents = mock(DocumentationGenerationService.class);
        service = new DocumentWorkflowService(workflows, audit, documents);
    }

    @Test
    void submissionIsStoredInTheDatabase() {
        documentVersions(0, 1);
        UUID id = service.create(OWNER, OWNER_AUTHORITIES, DOCUMENT_ID).id();

        service.submit(OWNER, OWNER_AUTHORITIES, id);
        DocumentWorkflow stored = reload(id);

        assertThat(stored.getStatus()).isEqualTo(DocumentWorkflowStatus.PENDING_STAFF_REVIEW);
        assertThat(stored.getSubmittedDocumentVersion()).isEqualTo(1);
        assertThat(stored.getSubmittedAt()).isNotNull();
        assertThat(stored.getOwnerUserId()).isEqualTo(OWNER);
        assertThat(column(id, "status")).isEqualTo("PENDING_STAFF_REVIEW");
        assertThat(((Number) column(id, "submitted_document_version")).intValue()).isEqualTo(1);
        // audit rows written in the same millisecond may share created_at: compare as a multiset
        assertThat(actions(id)).containsExactlyInAnyOrder("CREATED", "SUBMITTED");
    }

    @Test
    void resubmissionAfterChangesRequestedStoresTheNewVersionAndClearsTheOldReview() {
        documentVersions(0, 1);
        UUID id = service.create(OWNER, OWNER_AUTHORITIES, DOCUMENT_ID).id();
        service.submit(OWNER, OWNER_AUTHORITIES, id);
        service.claim(STAFF, STAFF_AUTHORITIES, id);
        service.staffReview(STAFF, STAFF_AUTHORITIES, id,
                new StaffReviewRequest(StaffReviewResult.CHANGES_REQUESTED, "Add the error codes"));

        DocumentWorkflow changes = reload(id);
        assertThat(changes.getStatus()).isEqualTo(DocumentWorkflowStatus.CHANGES_REQUESTED);
        assertThat(changes.getStaffComment()).isEqualTo("Add the error codes");
        assertThat(changes.getSubmittedDocumentVersion()).isEqualTo(1);

        documentVersions(0, 2);                     // the owner edited: version 2 is pending
        service.submit(OWNER, OWNER_AUTHORITIES, id);
        DocumentWorkflow resubmitted = reload(id);

        assertThat(resubmitted.getStatus()).isEqualTo(DocumentWorkflowStatus.PENDING_STAFF_REVIEW);
        assertThat(resubmitted.getSubmittedDocumentVersion()).isEqualTo(2);
        assertThat(resubmitted.getReviewerUserId()).isNull();
        assertThat(resubmitted.getStaffReviewResult()).isNull();
        assertThat(resubmitted.getStaffComment()).isNull();
        assertThat(((Number) column(id, "submitted_document_version")).intValue()).isEqualTo(2);
        assertThat(actions(id)).containsExactlyInAnyOrder("CREATED", "SUBMITTED", "CLAIMED",
                "CHANGES_REQUESTED", "SUBMITTED");
    }

    @Test
    void optimisticVersionGrowsWithEverySavedChange() {
        documentVersions(0, 1);
        UUID id = service.create(OWNER, OWNER_AUTHORITIES, DOCUMENT_ID).id();
        long created = reload(id).getOptimisticVersion();
        service.submit(OWNER, OWNER_AUTHORITIES, id);
        assertThat(reload(id).getOptimisticVersion()).isGreaterThan(created);
    }

    // ------------------------------------------------------------------ helpers

    /** The AI-service document as DocumentationGenerationService returns it. */
    private void documentVersions(int current, int pending) {
        ObjectNode document = JSON.createObjectNode();
        document.put("id", DOCUMENT_ID);
        document.put("title", "LD-402 document");
        document.put("owner_user_id", OWNER);
        document.put("current_version", current);
        document.put("pending_version", pending);
        when(documents.getDocument(OWNER, DOCUMENT_ID)).thenReturn(document);
    }

    /** The workflow as stored: the persistence context is flushed and emptied first. */
    private DocumentWorkflow reload(UUID id) {
        entityManager.flush();
        entityManager.clear();
        return workflows.findById(id).orElseThrow();
    }

    private Object column(UUID id, String column) {
        entityManager.flush();
        return entityManager.createNativeQuery(
                "SELECT " + column + " FROM document_workflows WHERE id = :id")
                .setParameter("id", id)
                .getSingleResult();
    }

    private List<String> actions(UUID id) {
        entityManager.flush();
        entityManager.clear();
        return audit.findByWorkflowIdOrderByCreatedAtAsc(id).stream()
                .map(DocumentWorkflowAudit::getAction)
                .toList();
    }
}
