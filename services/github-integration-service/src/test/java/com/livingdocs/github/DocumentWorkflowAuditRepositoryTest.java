package com.livingdocs.github;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import javax.sql.DataSource;

import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.MigrationVersion;
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.util.ReflectionTestUtils;

import com.livingdocs.github.entity.DocumentWorkflow;
import com.livingdocs.github.entity.DocumentWorkflowAudit;
import com.livingdocs.github.entity.DocumentWorkflowStatus;
import com.livingdocs.github.entity.ManagerDecision;
import com.livingdocs.github.entity.StaffReviewResult;
import com.livingdocs.github.repository.DocumentWorkflowAuditRepository;
import com.livingdocs.github.repository.DocumentWorkflowRepository;
import com.livingdocs.github.security.TokenEncryptor;
import com.livingdocs.github.service.DocumentWorkflowService;
import com.livingdocs.github.service.DocumentationGenerationService;

import jakarta.persistence.EntityManager;

@DataJpaTest(properties = "spring.flyway.enabled=true")
@ActiveProfiles("test")
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(DocumentWorkflowAuditRepositoryTest.TestTokenEncryptorConfiguration.class)
class DocumentWorkflowAuditRepositoryTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class TestTokenEncryptorConfiguration {
        @Bean
        TokenEncryptor testTokenEncryptor(@Value("${security.token-encryption-key}") String testKey) {
            return new TokenEncryptor(testKey);
        }
    }

    @Autowired
    private DocumentWorkflowRepository workflows;

    @Autowired
    private DocumentWorkflowAuditRepository audit;

    @Autowired
    private EntityManager entityManager;

    @Autowired
    private DataSource dataSource;

    @Autowired
    private Flyway flyway;

    @Test
    void persistsAndOrdersAuditHistoryIncludingLegacyNullRole() throws Exception {
        try (Connection connection = dataSource.getConnection()) {
            var database = connection.getMetaData();
            assertThat(database.getURL()).startsWith("jdbc:h2:mem:testdb");
            assertThat(database.getDatabaseProductName()).containsIgnoringCase("H2");
        }
        assertThat(flyway.info().applied())
                .extracting(migration -> migration.getVersion().getVersion())
                .contains("1", "2", "3", "4");

        DocumentWorkflow workflow = new DocumentWorkflow("audit-doc", "Audit document", "73");
        workflow.submit(1);
        workflow.claim("81");
        workflow.review(StaffReviewResult.PASSED, "Staff checks passed");
        workflow.decide("92", ManagerDecision.APPROVED, "Approved after review");
        workflow = workflows.saveAndFlush(workflow);

        Instant createdAt = Instant.parse("2026-01-01T10:00:00Z");
        Instant approvedAt = Instant.parse("2026-01-01T11:00:00Z");
        DocumentWorkflowAudit approval = new DocumentWorkflowAudit(workflow.getId(), "92", "APPROVED",
                "PENDING_MANAGER_APPROVAL", "APPROVED", "Approved after review",
                null, null, "MANAGER");
        ReflectionTestUtils.setField(approval, "createdAt", approvedAt);

        // Existing audit rows have no role snapshot; they must remain readable after V4.
        DocumentWorkflowAudit legacyCreated = new DocumentWorkflowAudit(workflow.getId(), "73", "CREATED",
                null, "DRAFT", null);
        ReflectionTestUtils.setField(legacyCreated, "createdAt", createdAt);

        // Persist newest first so this assertion proves the repository orders by event time.
        audit.saveAndFlush(approval);
        audit.saveAndFlush(legacyCreated);
        entityManager.clear();

        List<DocumentWorkflowAudit> history = audit.findByWorkflowIdOrderByCreatedAtAsc(workflow.getId());

        assertThat(history).hasSize(2);
        assertThat(history).extracting(DocumentWorkflowAudit::getAction)
                .containsExactly("CREATED", "APPROVED");
        assertThat(history.get(0).getActorUserId()).isEqualTo("73");
        assertThat(history.get(0).getActorRole()).isNull();
        assertThat(history.get(0).getCreatedAt()).isEqualTo(createdAt);
        assertThat(history.get(1).getActorUserId()).isEqualTo("92");
        assertThat(history.get(1).getActorRole()).isEqualTo("MANAGER");
        assertThat(history.get(1).getPreviousStatus()).isEqualTo("PENDING_MANAGER_APPROVAL");
        assertThat(history.get(1).getNewStatus()).isEqualTo("APPROVED");
        assertThat(history.get(1).getComment()).isEqualTo("Approved after review");
        assertThat(history.get(1).getCreatedAt()).isEqualTo(approvedAt);
    }

    @Test
    void v4PreservesAuditRowsCreatedByV3() throws Exception {
        String url = "jdbc:h2:mem:ld256_v4_" + UUID.randomUUID().toString().replace("-", "")
                + ";MODE=PostgreSQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1";
        Flyway v3 = Flyway.configure()
                .dataSource(url, "sa", "")
                .locations("classpath:db/migration")
                .target(MigrationVersion.fromVersion("3"))
                .load();
        v3.migrate();

        UUID workflowId = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();
        try (Connection connection = DriverManager.getConnection(url, "sa", "")) {
            try (PreparedStatement workflow = connection.prepareStatement("""
                    INSERT INTO document_workflows
                        (id, document_id, document_title, owner_user_id, status, created_at, updated_at)
                    VALUES (?, 'legacy-doc', 'Legacy document', '73', 'APPROVED', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """)) {
                workflow.setObject(1, workflowId);
                workflow.executeUpdate();
            }
            try (PreparedStatement event = connection.prepareStatement("""
                    INSERT INTO document_workflow_audit
                        (id, workflow_id, actor_user_id, action, previous_status, new_status, comment, created_at)
                    VALUES (?, ?, '92', 'APPROVED', 'PENDING_MANAGER_APPROVAL', 'APPROVED',
                            'Historical approval', CURRENT_TIMESTAMP)
                    """)) {
                event.setObject(1, eventId);
                event.setObject(2, workflowId);
                event.executeUpdate();
            }
        }

        Flyway v4 = Flyway.configure().dataSource(url, "sa", "")
                .locations("classpath:db/migration").load();
        v4.migrate();

        try (Connection connection = DriverManager.getConnection(url, "sa", "");
             PreparedStatement query = connection.prepareStatement(
                     "SELECT actor_user_id, actor_role, action, comment FROM document_workflow_audit WHERE id = ?")) {
            query.setObject(1, eventId);
            try (ResultSet result = query.executeQuery()) {
                assertThat(result.next()).isTrue();
                assertThat(result.getString("actor_user_id")).isEqualTo("92");
                assertThat(result.getString("actor_role")).isNull();
                assertThat(result.getString("action")).isEqualTo("APPROVED");
                assertThat(result.getString("comment")).isEqualTo("Historical approval");
                assertThat(result.next()).isFalse();
            }
        }
    }

    @Test
    void historyAccessibleQueryKeepsEachRoleWithinReadableWorkflowBoundaries() {
        DocumentWorkflow ownedDraft = new DocumentWorkflow("owned-draft", "Owned draft", "developer-1");
        DocumentWorkflow unrelatedDraft = new DocumentWorkflow("unrelated-draft", "Other draft", "developer-2");

        DocumentWorkflow pendingStaff = submitted("pending-staff", "owner-1");
        DocumentWorkflow pendingStaffCurrentReviewer = submitted("pending-current-reviewer", "owner-9");
        ReflectionTestUtils.setField(pendingStaffCurrentReviewer, "reviewerUserId", "staff-1");
        DocumentWorkflow pendingStaffOtherReviewer = submitted("pending-other-reviewer", "owner-10");
        ReflectionTestUtils.setField(pendingStaffOtherReviewer, "reviewerUserId", "staff-2");
        DocumentWorkflow assignedReview = submitted("assigned-review", "owner-2");
        assignedReview.claim("staff-1");
        DocumentWorkflow assignedCompleted = submitted("assigned-completed", "owner-3");
        assignedCompleted.claim("staff-1");
        assignedCompleted.review(StaffReviewResult.CHANGES_REQUESTED, "Needs changes");
        DocumentWorkflow assignedApproved = submitted("assigned-approved", "owner-8");
        assignedApproved.claim("staff-1");
        assignedApproved.review(StaffReviewResult.PASSED, "Passed");
        assignedApproved.decide("manager-3", ManagerDecision.APPROVED, "Approved");
        DocumentWorkflow otherStaffCompleted = submitted("other-staff-completed", "owner-4");
        otherStaffCompleted.claim("staff-2");
        otherStaffCompleted.review(StaffReviewResult.CHANGES_REQUESTED, "Needs changes");

        DocumentWorkflow managerPending = passedStaffReview("manager-pending", "owner-5");
        DocumentWorkflow approved = passedStaffReview("approved", "owner-6");
        approved.decide("manager-1", ManagerDecision.APPROVED, "Approved");
        DocumentWorkflow rejected = passedStaffReview("rejected", "owner-7");
        rejected.decide("manager-2", ManagerDecision.REJECTED, "Rejected");

        workflows.saveAllAndFlush(List.of(ownedDraft, unrelatedDraft, pendingStaff, pendingStaffCurrentReviewer,
                pendingStaffOtherReviewer, assignedReview, assignedCompleted, assignedApproved,
                otherStaffCompleted, managerPending, approved, rejected));
        List<DocumentWorkflowStatus> managerStatuses = List.of(DocumentWorkflowStatus.PENDING_MANAGER_APPROVAL,
                DocumentWorkflowStatus.APPROVED, DocumentWorkflowStatus.REJECTED);
        Sort stableSort = Sort.by(Sort.Order.desc("createdAt"), Sort.Order.asc("id"));

        Page<DocumentWorkflow> developerResults = workflows.findHistoryAccessible("developer-1",
                true, false, false, false, DocumentWorkflowStatus.PENDING_STAFF_REVIEW,
                DocumentWorkflowStatus.STAFF_REVIEWING, managerStatuses, PageRequest.of(0, 20, stableSort));
        assertThat(developerResults).extracting(w -> w.getDocumentId()).containsExactly("owned-draft");

        Page<DocumentWorkflow> staffResults = workflows.findHistoryAccessible("staff-1",
                false, true, true, false, DocumentWorkflowStatus.PENDING_STAFF_REVIEW,
                DocumentWorkflowStatus.STAFF_REVIEWING, managerStatuses, PageRequest.of(0, 20, stableSort));
        assertThat(staffResults).extracting(w -> w.getDocumentId()).containsExactlyInAnyOrder(
                "pending-staff", "pending-current-reviewer", "assigned-review",
                "assigned-completed", "assigned-approved");
        assertThat(staffResults).extracting(w -> w.getDocumentId()).doesNotContain("pending-other-reviewer");

        Page<DocumentWorkflow> managerResults = workflows.findHistoryAccessible("manager-1",
                false, false, false, true, DocumentWorkflowStatus.PENDING_STAFF_REVIEW,
                DocumentWorkflowStatus.STAFF_REVIEWING, managerStatuses, PageRequest.of(0, 20, stableSort));
        assertThat(managerResults).extracting(w -> w.getDocumentId()).containsExactlyInAnyOrder(
                "manager-pending", "assigned-approved", "approved", "rejected");
        Page<DocumentWorkflow> firstManagerPage = workflows.findHistoryAccessible("manager-1",
                false, false, false, true, DocumentWorkflowStatus.PENDING_STAFF_REVIEW,
                DocumentWorkflowStatus.STAFF_REVIEWING, managerStatuses, PageRequest.of(0, 1, stableSort));
        assertThat(firstManagerPage.getContent()).hasSize(1);
        assertThat(firstManagerPage.getTotalElements()).isEqualTo(4);
        assertThat(firstManagerPage.getTotalPages()).isEqualTo(4);

        DocumentWorkflowService service = new DocumentWorkflowService(workflows, audit,
                org.mockito.Mockito.mock(DocumentationGenerationService.class));
        var developerHistory = service.historyAccessible("developer-1",
                java.util.Set.of("ROLE_DEVELOPER", "DOCUMENT_VIEW"), 0, 20);
        developerHistory.content().forEach(w -> assertThat(service.history("developer-1",
                java.util.Set.of("ROLE_DEVELOPER", "DOCUMENT_VIEW"), w.id())).isNotNull());
        java.util.Set<String> customQueueAuthorities = java.util.Set.of(
                "ROLE_CUSTOM_QUEUE", "DOCUMENT_REVIEW_QUEUE_VIEW");
        var staffQueueHistory = service.historyAccessible("staff-1", customQueueAuthorities, 0, 20);
        assertThat(staffQueueHistory.content()).extracting(w -> w.documentId()).contains(
                "pending-staff", "pending-current-reviewer", "assigned-review");
        staffQueueHistory.content().forEach(w -> assertThat(service.history("staff-1",
                customQueueAuthorities, w.id())).isNotNull());
        assertThatThrownBy(() -> service.history("staff-1", customQueueAuthorities,
                pendingStaffOtherReviewer.getId()))
                .isInstanceOf(com.livingdocs.github.exception.ApiException.class);

        java.util.Set<String> customAssignedReviewAuthorities = java.util.Set.of(
                "ROLE_CUSTOM_AUDITOR", "DOCUMENT_REVIEW");
        var assignedReviewHistory = service.historyAccessible("staff-1", customAssignedReviewAuthorities, 0, 20);
        assertThat(assignedReviewHistory.content()).extracting(w -> w.documentId()).contains(
                "pending-current-reviewer", "assigned-review", "assigned-completed", "assigned-approved");
        assignedReviewHistory.content().forEach(w -> assertThat(service.history("staff-1",
                customAssignedReviewAuthorities, w.id())).isNotNull());

        java.util.Set<String> customManagerAuthorities = java.util.Set.of(
                "ROLE_CUSTOM_APPROVER", "DOCUMENT_APPROVAL_QUEUE_VIEW");
        var managerHistory = service.historyAccessible("manager-1",
                customManagerAuthorities, 0, 20);
        managerHistory.content().forEach(w -> assertThat(service.history("manager-1",
                customManagerAuthorities, w.id())).isNotNull());
    }

    private static DocumentWorkflow submitted(String documentId, String ownerId) {
        DocumentWorkflow workflow = new DocumentWorkflow(documentId, documentId, ownerId);
        workflow.submit(1);
        return workflow;
    }

    private static DocumentWorkflow passedStaffReview(String documentId, String ownerId) {
        DocumentWorkflow workflow = submitted(documentId, ownerId);
        workflow.claim("staff-reviewer");
        workflow.review(StaffReviewResult.PASSED, "Passed");
        return workflow;
    }
}
