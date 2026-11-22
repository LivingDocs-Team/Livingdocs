package com.livingdocs.github;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

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
import com.livingdocs.github.config.FlywayMigrationLineageConfig;
import com.livingdocs.github.config.FlywayMigrationLineageSelector;
import com.livingdocs.github.dto.WorkflowDtos.AuditResponse;
import com.livingdocs.github.dto.WorkflowDtos.StaffReviewRequest;
import com.livingdocs.github.dto.WorkflowDtos.WorkflowResponse;
import com.livingdocs.github.entity.DocumentWorkflowStatus;
import com.livingdocs.github.entity.ManagerDecision;
import com.livingdocs.github.entity.StaffReviewResult;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.repository.DocumentWorkflowAuditRepository;
import com.livingdocs.github.repository.DocumentWorkflowRepository;
import com.livingdocs.github.security.TokenEncryptor;
import com.livingdocs.github.service.DocumentWorkflowService;
import com.livingdocs.github.service.DocumentationGenerationService;

/**
 * LD-403: end-to-end regression of the staff-to-manager workflow on the real service and the
 * real repositories (H2 + Flyway). Only the AI service is replaced, by a small stateful fake of
 * the document store that mimics the proposed -> accepted/dismissed version lifecycle.
 */
@DataJpaTest(properties = "spring.flyway.enabled=true")
@ActiveProfiles("test")
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Import({DocumentWorkflowEndToEndTest.TestTokenEncryptorConfiguration.class,
        FlywayMigrationLineageConfig.class, FlywayMigrationLineageSelector.class})
class DocumentWorkflowEndToEndTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class TestTokenEncryptorConfiguration {
        @Bean
        TokenEncryptor testTokenEncryptor(@Value("${security.token-encryption-key}") String testKey) {
            return new TokenEncryptor(testKey);
        }
    }

    private static final String OWNER = "73";
    private static final String STAFF = "81";
    private static final String OTHER_STAFF = "82";
    private static final String MANAGER = "92";

    private static final Set<String> DEVELOPER_AUTH = Set.of("ROLE_DEVELOPER",
            "DOCUMENT_VIEW", "DOCUMENT_CREATE", "DOCUMENT_UPDATE", "DOCUMENT_SUBMIT");
    private static final Set<String> STAFF_AUTH = Set.of("ROLE_STAFF",
            "DOCUMENT_REVIEW_QUEUE_VIEW", "DOCUMENT_CLAIM", "DOCUMENT_RELEASE", "DOCUMENT_REVIEW");
    private static final Set<String> MANAGER_AUTH = Set.of("ROLE_MANAGER",
            "DOCUMENT_APPROVAL_QUEUE_VIEW", "DOCUMENT_APPROVE", "DOCUMENT_REJECT", "DOCUMENT_ROLLBACK");

    @Autowired
    private DocumentWorkflowRepository workflows;
    @Autowired
    private DocumentWorkflowAuditRepository audit;

    private DocumentationGenerationService documents;
    private DocumentWorkflowService service;

    /**
     * State of the single document held by the fake AI service. By default the document already
     * has an accepted version 1 and a new proposed version 2 (for example an AI update): this is
     * the state in which DocumentWorkflowService.submit works today. The state of a document that
     * was just saved from a generation job (current 0, pending 1) is covered by
     * {@link #firstSubmissionOfNewlySavedDocumentIsAccepted()}.
     */
    private final AtomicInteger currentVersion = new AtomicInteger(1);
    private final AtomicInteger pendingVersion = new AtomicInteger(2);

    @BeforeEach
    void setUp() throws Exception {
        currentVersion.set(1);
        pendingVersion.set(2);
        documents = mock(DocumentationGenerationService.class);
        ObjectMapper mapper = new ObjectMapper();
        when(documents.getDocument(anyString(), eq("doc-e2e"))).thenAnswer(call -> {
            ObjectNode node = mapper.createObjectNode();
            node.put("id", "doc-e2e");
            node.put("title", "End to end guide");
            node.put("owner_user_id", OWNER);
            node.put("current_version", currentVersion.get());
            if (pendingVersion.get() > 0) {
                node.put("pending_version", pendingVersion.get());
            } else {
                node.putNull("pending_version");
            }
            node.put("versions_total", Math.max(currentVersion.get(), pendingVersion.get()));
            return node;
        });
        doAnswer(call -> {
            int version = call.getArgument(3, Integer.class);
            String decision = call.getArgument(4, String.class);
            if (version == pendingVersion.get()) {
                if ("APPROVED".equals(decision)) {
                    currentVersion.set(version);
                }
                pendingVersion.set(0);
            }
            return null;
        }).when(documents).resolveDocumentVersion(anyString(), anyString(), eq("doc-e2e"), anyInt(),
                anyString(), any());
        service = new DocumentWorkflowService(workflows, audit, documents);
    }

    // ---------- happy path ----------

    @Test
    void submitClaimStaffReviewManagerApprovalIsPersistedAndAuditedInOrder() {
        UUID id = createWorkflow();
        assertThat(service.get(OWNER, DEVELOPER_AUTH, id).status()).isEqualTo(DocumentWorkflowStatus.DRAFT);

        WorkflowResponse submitted = service.submit(OWNER, DEVELOPER_AUTH, id);
        assertThat(submitted.status()).isEqualTo(DocumentWorkflowStatus.PENDING_STAFF_REVIEW);
        assertThat(submitted.submittedDocumentVersion()).isEqualTo(2);
        assertThat(service.staffQueue(STAFF, STAFF_AUTH, 0, 20).content())
                .extracting(WorkflowResponse::id).contains(id);

        WorkflowResponse claimed = service.claim(STAFF, STAFF_AUTH, id);
        assertThat(claimed.status()).isEqualTo(DocumentWorkflowStatus.STAFF_REVIEWING);
        assertThat(claimed.reviewerUserId()).isEqualTo(STAFF);

        WorkflowResponse reviewed = service.staffReview(STAFF, STAFF_AUTH, id,
                new StaffReviewRequest(StaffReviewResult.PASSED, "Matches the source code"));
        assertThat(reviewed.status()).isEqualTo(DocumentWorkflowStatus.PENDING_MANAGER_APPROVAL);
        assertThat(reviewed.staffReviewResult()).isEqualTo(StaffReviewResult.PASSED);
        assertThat(service.managerQueue(MANAGER_AUTH, 0, 20).content())
                .extracting(WorkflowResponse::id).contains(id);

        WorkflowResponse approved = service.decide(MANAGER, MANAGER_AUTH, id,
                ManagerDecision.APPROVED, "Approved for publishing");
        assertThat(approved.status()).isEqualTo(DocumentWorkflowStatus.APPROVED);
        assertThat(approved.managerUserId()).isEqualTo(MANAGER);
        assertThat(approved.managerDecision()).isEqualTo(ManagerDecision.APPROVED);
        assertThat(currentVersion.get()).isEqualTo(2);
        assertThat(pendingVersion.get()).isZero();
        assertThat(service.managerQueue(MANAGER_AUTH, 0, 20).content())
                .extracting(WorkflowResponse::id).doesNotContain(id);

        List<AuditResponse> history = service.history(OWNER, DEVELOPER_AUTH, id);
        assertThat(history).extracting(AuditResponse::action)
                .containsExactly("CREATED", "SUBMITTED", "CLAIMED", "PASSED", "APPROVED");
        assertThat(history).extracting(AuditResponse::actorUserId)
                .containsExactly(OWNER, OWNER, STAFF, STAFF, MANAGER);
        assertThat(history).extracting(AuditResponse::previousStatus)
                .containsExactly(null, "DRAFT", "PENDING_STAFF_REVIEW", "STAFF_REVIEWING",
                        "PENDING_MANAGER_APPROVAL");
        assertThat(history).extracting(AuditResponse::newStatus)
                .containsExactly("DRAFT", "PENDING_STAFF_REVIEW", "STAFF_REVIEWING",
                        "PENDING_MANAGER_APPROVAL", "APPROVED");
        assertThat(history.get(3).comment()).isEqualTo("Matches the source code");
        assertThat(history.get(4).comment()).isEqualTo("Approved for publishing");
        assertThat(history).extracting(AuditResponse::actorRole)
                .containsExactly("DEVELOPER", "DEVELOPER", "STAFF", "STAFF", "MANAGER");
        assertThat(history).extracting(AuditResponse::documentVersion).containsOnly(2);
        assertThat(history).extracting(AuditResponse::triggerSource).containsOnly("REVIEW_WORKFLOW");
        assertThat(history).allSatisfy(event -> assertThat(event.createdAt()).isNotNull());
        assertThat(history).extracting(AuditResponse::createdAt).isSorted();
    }

    // ---------- reject path ----------

    @Test
    void managerRejectionIsPersistedAuditedWithReasonAndIsFinal() {
        UUID id = workflowReadyForManager();

        assertThatThrownBy(() -> service.decide(MANAGER, MANAGER_AUTH, id, ManagerDecision.REJECTED, "  "))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(400));
        assertThat(service.get(MANAGER, MANAGER_AUTH, id).status())
                .isEqualTo(DocumentWorkflowStatus.PENDING_MANAGER_APPROVAL);

        WorkflowResponse rejected = service.decide(MANAGER, MANAGER_AUTH, id, ManagerDecision.REJECTED,
                "Endpoints are missing from the guide");
        assertThat(rejected.status()).isEqualTo(DocumentWorkflowStatus.REJECTED);
        assertThat(rejected.managerComment()).isEqualTo("Endpoints are missing from the guide");
        assertThat(currentVersion.get()).isEqualTo(1);   // the previously approved version stays current
        assertThat(pendingVersion.get()).isZero();

        List<AuditResponse> history = service.history(OWNER, DEVELOPER_AUTH, id);
        AuditResponse last = history.get(history.size() - 1);
        assertThat(last.action()).isEqualTo("REJECTED");
        assertThat(last.actorUserId()).isEqualTo(MANAGER);
        assertThat(last.actorRole()).isEqualTo("MANAGER");
        assertThat(last.previousStatus()).isEqualTo("PENDING_MANAGER_APPROVAL");
        assertThat(last.newStatus()).isEqualTo("REJECTED");
        assertThat(last.comment()).isEqualTo("Endpoints are missing from the guide");

        // Documented current behaviour: REJECTED is terminal. submit() only accepts DRAFT or
        // CHANGES_REQUESTED, so the owner cannot resubmit and the manager cannot decide again.
        assertThatThrownBy(() -> service.submit(OWNER, DEVELOPER_AUTH, id))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(409));
        assertThatThrownBy(() -> service.decide(MANAGER, MANAGER_AUTH, id, ManagerDecision.APPROVED, null))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(409));
    }

    @Test
    void staffChangesRequestedLetsOwnerResubmitAndHistoryKeepsBothRounds() {
        UUID id = createWorkflow();
        service.submit(OWNER, DEVELOPER_AUTH, id);
        service.claim(STAFF, STAFF_AUTH, id);

        assertThatThrownBy(() -> service.staffReview(STAFF, STAFF_AUTH, id,
                new StaffReviewRequest(StaffReviewResult.CHANGES_REQUESTED, " ")))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(400));

        WorkflowResponse changes = service.staffReview(STAFF, STAFF_AUTH, id,
                new StaffReviewRequest(StaffReviewResult.CHANGES_REQUESTED, "Explain the setup"));
        assertThat(changes.status()).isEqualTo(DocumentWorkflowStatus.CHANGES_REQUESTED);

        // The owner edits in the AI service (a new pending version 3) and resubmits.
        pendingVersion.set(3);
        WorkflowResponse resubmitted = service.submit(OWNER, DEVELOPER_AUTH, id);
        assertThat(resubmitted.status()).isEqualTo(DocumentWorkflowStatus.PENDING_STAFF_REVIEW);
        assertThat(resubmitted.submittedDocumentVersion()).isEqualTo(3);
        assertThat(resubmitted.reviewerUserId()).isNull();
        assertThat(resubmitted.staffReviewResult()).isNull();

        assertThat(service.history(OWNER, DEVELOPER_AUTH, id)).extracting(AuditResponse::action)
                .containsExactly("CREATED", "SUBMITTED", "CLAIMED", "CHANGES_REQUESTED", "SUBMITTED");
    }

    // ---------- first submission of a newly saved document (LD-403 fix) ----------

    /**
     * The AI service saves a user's generated document as current_version 0 + pending_version 1
     * (ai-service/app/versions.py create_from_job). The very first submission of such a document
     * must be accepted and then go through the whole workflow. Before the LD-403 fix
     * documentVersionForSubmit required current_version >= 1 and answered 409
     * "The document has no readable version."
     */
    @Test
    void firstSubmissionOfNewlySavedDocumentIsAccepted() {
        currentVersion.set(0);
        pendingVersion.set(1);
        UUID id = createWorkflow();

        WorkflowResponse submitted = service.submit(OWNER, DEVELOPER_AUTH, id);

        assertThat(submitted.status()).isEqualTo(DocumentWorkflowStatus.PENDING_STAFF_REVIEW);
        assertThat(submitted.submittedDocumentVersion()).isEqualTo(1);

        service.claim(STAFF, STAFF_AUTH, id);
        service.staffReview(STAFF, STAFF_AUTH, id, new StaffReviewRequest(StaffReviewResult.PASSED, "ok"));
        WorkflowResponse approved = service.decide(MANAGER, MANAGER_AUTH, id, ManagerDecision.APPROVED, null);
        assertThat(approved.status()).isEqualTo(DocumentWorkflowStatus.APPROVED);
        assertThat(currentVersion.get()).isEqualTo(1);   // the first version became the approved one
        assertThat(pendingVersion.get()).isZero();
    }

    @Test
    void documentWithNeitherAnApprovedNorAPendingVersionCannotBeSubmitted() {
        currentVersion.set(0);
        pendingVersion.set(0);
        UUID id = createWorkflow();
        long eventsBefore = audit.count();

        assertThatThrownBy(() -> service.submit(OWNER, DEVELOPER_AUTH, id))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(409))
                .hasMessage("The document has no readable version.");
        assertThat(service.get(OWNER, DEVELOPER_AUTH, id).status()).isEqualTo(DocumentWorkflowStatus.DRAFT);
        assertThat(audit.count()).isEqualTo(eventsBefore);
    }

    @Test
    void approvedDocumentWithoutPendingVersionStillSubmitsItsCurrentVersion() {
        currentVersion.set(3);
        pendingVersion.set(0);
        UUID id = createWorkflow();

        assertThat(service.submit(OWNER, DEVELOPER_AUTH, id).submittedDocumentVersion()).isEqualTo(3);
    }

    // ---------- unauthorized / invalid scenarios ----------

    @Test
    void usersWithoutTheStaffRoleCannotClaimOrReviewAndStaffCannotDecide() {
        UUID id = submittedWorkflow();

        for (Set<String> notStaff : List.of(DEVELOPER_AUTH, MANAGER_AUTH,
                Set.of("ROLE_ADMINISTRATOR", "DOCUMENT_CLAIM", "DOCUMENT_REVIEW"))) {
            assertThatThrownBy(() -> service.claim("55", withClaim(notStaff), id))
                    .isInstanceOf(ApiException.class)
                    .satisfies(error -> assertThat(status(error)).isEqualTo(403));
        }
        service.claim(STAFF, STAFF_AUTH, id);
        assertThatThrownBy(() -> service.staffReview(MANAGER, withReview(MANAGER_AUTH), id,
                new StaffReviewRequest(StaffReviewResult.PASSED, null)))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(403));
        service.staffReview(STAFF, STAFF_AUTH, id, new StaffReviewRequest(StaffReviewResult.PASSED, "ok"));

        Set<String> staffWithDecisionPermissions = Set.of("ROLE_STAFF", "DOCUMENT_APPROVE", "DOCUMENT_REJECT");
        assertThatThrownBy(() -> service.decide(STAFF, staffWithDecisionPermissions, id,
                ManagerDecision.APPROVED, null))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(403));
        assertThatThrownBy(() -> service.decide(OWNER, DEVELOPER_AUTH, id, ManagerDecision.APPROVED, null))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(403));
        assertThat(service.get(MANAGER, MANAGER_AUTH, id).status())
                .isEqualTo(DocumentWorkflowStatus.PENDING_MANAGER_APPROVAL);
    }

    @Test
    void secondStaffCannotClaimOrReviewAnAlreadyClaimedWorkflow() {
        UUID id = submittedWorkflow();
        service.claim(STAFF, STAFF_AUTH, id);

        assertThatThrownBy(() -> service.claim(OTHER_STAFF, STAFF_AUTH, id))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(409));
        assertThatThrownBy(() -> service.staffReview(OTHER_STAFF, STAFF_AUTH, id,
                new StaffReviewRequest(StaffReviewResult.PASSED, null)))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(403));
        assertThat(service.get(STAFF, STAFF_AUTH, id).reviewerUserId()).isEqualTo(STAFF);
    }

    @Test
    void invalidTransitionsAreRejectedAndWriteNoAuditEvent() {
        UUID id = createWorkflow();
        long eventsAfterCreate = audit.count();

        // Draft: cannot be claimed (409) or reviewed (403, no assigned reviewer).
        assertThatThrownBy(() -> service.claim(STAFF, STAFF_AUTH, id))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(409));
        assertThatThrownBy(() -> service.staffReview(STAFF, STAFF_AUTH, id,
                new StaffReviewRequest(StaffReviewResult.PASSED, null)))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(403));
        assertThatThrownBy(() -> service.decide(MANAGER, MANAGER_AUTH, id, ManagerDecision.APPROVED, null))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(409));

        // Submitted but not reviewed: the manager cannot approve before the staff review passes.
        service.submit(OWNER, DEVELOPER_AUTH, id);
        eventsAfterCreate = audit.count();
        assertThatThrownBy(() -> service.decide(MANAGER, MANAGER_AUTH, id, ManagerDecision.APPROVED, null))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(409));
        assertThatThrownBy(() -> service.submit(OWNER, DEVELOPER_AUTH, id))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(409));
        assertThat(audit.count()).isEqualTo(eventsAfterCreate);

        // Finalized: nothing can act on an approved workflow any more.
        service.claim(STAFF, STAFF_AUTH, id);
        service.staffReview(STAFF, STAFF_AUTH, id, new StaffReviewRequest(StaffReviewResult.PASSED, null));
        service.decide(MANAGER, MANAGER_AUTH, id, ManagerDecision.APPROVED, null);
        long eventsAfterApproval = audit.count();
        assertThatThrownBy(() -> service.claim(STAFF, STAFF_AUTH, id))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(409));
        assertThatThrownBy(() -> service.staffReview(STAFF, STAFF_AUTH, id,
                new StaffReviewRequest(StaffReviewResult.PASSED, null)))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(403));
        assertThatThrownBy(() -> service.decide(MANAGER, MANAGER_AUTH, id, ManagerDecision.REJECTED, "late"))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(409));
        assertThat(audit.count()).isEqualTo(eventsAfterApproval);
    }

    @Test
    void auditHistoryIsHiddenFromUsersWhoCannotReadTheWorkflow() {
        UUID id = workflowReadyForManager();

        assertThatThrownBy(() -> service.history("999", DEVELOPER_AUTH, id))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(404));
        assertThatThrownBy(() -> service.history(OTHER_STAFF, STAFF_AUTH, id))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(status(error)).isEqualTo(404));
        assertThat(service.history(MANAGER, MANAGER_AUTH, id)).isNotEmpty();
        assertThat(service.history(OWNER, DEVELOPER_AUTH, id)).isNotEmpty();
    }

    // ---------- helpers ----------

    private UUID createWorkflow() {
        return service.create(OWNER, DEVELOPER_AUTH, "doc-e2e").id();
    }

    private UUID submittedWorkflow() {
        UUID id = createWorkflow();
        service.submit(OWNER, DEVELOPER_AUTH, id);
        return id;
    }

    private UUID workflowReadyForManager() {
        UUID id = submittedWorkflow();
        service.claim(STAFF, STAFF_AUTH, id);
        service.staffReview(STAFF, STAFF_AUTH, id,
                new StaffReviewRequest(StaffReviewResult.PASSED, "Looks correct"));
        return id;
    }

    private static Set<String> withClaim(Set<String> base) {
        java.util.HashSet<String> result = new java.util.HashSet<>(base);
        result.add("DOCUMENT_CLAIM");
        return result;
    }

    private static Set<String> withReview(Set<String> base) {
        java.util.HashSet<String> result = new java.util.HashSet<>(base);
        result.add("DOCUMENT_REVIEW");
        return result;
    }

    private static int status(Throwable error) {
        return ((ApiException) error).getStatus().value();
    }
}
