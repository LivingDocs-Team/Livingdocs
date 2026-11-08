package com.livingdocs.github;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.List;
import java.lang.reflect.Field;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.data.jpa.repository.Lock;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.dto.WorkflowDtos.StaffReviewRequest;
import com.livingdocs.github.dto.WorkflowDtos.ReassignRequest;
import com.livingdocs.github.entity.DocumentWorkflow;
import com.livingdocs.github.entity.DocumentWorkflowAudit;
import com.livingdocs.github.entity.DocumentWorkflowStatus;
import com.livingdocs.github.entity.ManagerDecision;
import com.livingdocs.github.entity.StaffReviewResult;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.repository.DocumentWorkflowAuditRepository;
import com.livingdocs.github.repository.DocumentWorkflowRepository;
import com.livingdocs.github.service.DocumentWorkflowService;
import com.livingdocs.github.service.DocumentationGenerationService;

class DocumentWorkflowServiceTest {
    private static final String OWNER = "73";
    private static final String REVIEWER = "81";
    private static final String MANAGER = "92";
    private static final UUID ID = UUID.fromString("11111111-1111-1111-1111-111111111111");

    private DocumentWorkflowRepository workflows;
    private DocumentWorkflowAuditRepository audit;
    private DocumentationGenerationService documents;
    private DocumentWorkflowService service;

    @BeforeEach
    void setUp() {
        workflows = mock(DocumentWorkflowRepository.class);
        audit = mock(DocumentWorkflowAuditRepository.class);
        documents = mock(DocumentationGenerationService.class);
        service = new DocumentWorkflowService(workflows, audit, documents);
    }

    @Test
    void legacyDocumentWithoutVerifiedOwnerCannotEnterWorkflow() throws Exception {
        when(documents.getDocument(OWNER, "legacy-doc")).thenReturn(new ObjectMapper().readTree(
                "{\"id\":\"legacy-doc\",\"owner_user_id\":null}"));

        assertThatThrownBy(() -> service.create(OWNER, Set.of("DOCUMENT_CREATE"), "legacy-doc"))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(404));
        verify(workflows, never()).saveAndFlush(any());
    }

    @Test
    void staffMustBeAssignedAndCannotMakeManagerDecision() throws Exception {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));

        assertThatThrownBy(() -> service.staffReview("99", Set.of("ROLE_STAFF", "DOCUMENT_REVIEW"), ID,
                new StaffReviewRequest(StaffReviewResult.PASSED, null)))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(403));

        assertThatThrownBy(() -> service.decide(REVIEWER,
                Set.of("ROLE_STAFF", "DOCUMENT_APPROVE"), ID, ManagerDecision.APPROVED, null))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(403));
    }

    @Test
    void managerCannotApproveUntilStaffReviewPassesAndReviewerCannotApproveOwnReview() throws Exception {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));

        assertThatThrownBy(() -> service.decide(MANAGER,
                Set.of("ROLE_MANAGER", "DOCUMENT_APPROVE"), ID, ManagerDecision.APPROVED, null))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(409));

        assertThatThrownBy(() -> service.decide(MANAGER,
                Set.of("ROLE_MANAGER", "DOCUMENT_REJECT"), ID, ManagerDecision.REJECTED, "No staff review"))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(409));

        workflow.review(StaffReviewResult.PASSED, "Checks passed");
        assertThatThrownBy(() -> service.decide(REVIEWER,
                Set.of("ROLE_MANAGER", "DOCUMENT_APPROVE"), ID, ManagerDecision.APPROVED, null))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(403));
    }

    @Test
    void onlyManagerWithMatchingPermissionCanMakeFinalDecision() {
        for (ManagerDecision decision : ManagerDecision.values()) {
            String permission = decision == ManagerDecision.APPROVED ? "DOCUMENT_APPROVE" : "DOCUMENT_REJECT";
            for (String role : List.of("ROLE_ADMINISTRATOR", "ROLE_ADMIN", "ROLE_STAFF", "ROLE_DEVELOPER")) {
                assertThatThrownBy(() -> service.decide("actor-1", Set.of(role, permission), ID, decision,
                        decision == ManagerDecision.REJECTED ? "Rejected" : null))
                        .as("%s with %s must not decide", role, permission)
                        .isInstanceOf(ApiException.class)
                        .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(403));
            }
            assertThatThrownBy(() -> service.decide(MANAGER, Set.of("ROLE_MANAGER"), ID, decision,
                    decision == ManagerDecision.REJECTED ? "Rejected" : null))
                    .as("Manager missing %s must be denied", permission)
                    .isInstanceOf(ApiException.class)
                    .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(403));
        }
    }

    @Test
    void successfulStaffReviewThenManagerDecisionIsAudited() throws Exception {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        when(documents.getDocument(MANAGER, "doc-1")).thenReturn(new ObjectMapper().readTree(
                "{\"id\":\"doc-1\",\"owner_user_id\":\"73\",\"current_version\":1,\"pending_version\":null}"));
        when(workflows.saveAndFlush(workflow)).thenReturn(workflow);

        var reviewed = service.staffReview(REVIEWER,
                Set.of("ROLE_STAFF", "DOCUMENT_REVIEW"), ID,
                new StaffReviewRequest(StaffReviewResult.PASSED, "All checks passed"));
        var decided = service.decide(MANAGER,
                Set.of("ROLE_MANAGER", "DOCUMENT_APPROVE"), ID, ManagerDecision.APPROVED, "Approved");

        assertThat(reviewed.status()).isEqualTo(DocumentWorkflowStatus.PENDING_MANAGER_APPROVAL);
        assertThat(decided.status()).isEqualTo(DocumentWorkflowStatus.APPROVED);
        assertThatThrownBy(() -> service.decide(MANAGER,
                Set.of("ROLE_MANAGER", "DOCUMENT_REJECT"), ID, ManagerDecision.REJECTED, "Changed my mind"))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(409));
        verify(audit, org.mockito.Mockito.times(2)).save(any(DocumentWorkflowAudit.class));
        verify(documents, never()).resolveDocumentVersion(any(), any(), any(), any(Integer.class), any(), any());
    }

    @Test
    void developerCanSubmitOwnedDocumentButDuplicateSubmissionIsRejected() throws Exception {
        DocumentWorkflow workflow = new DocumentWorkflow("doc-1", "Document", OWNER);
        ReflectionTestUtils.setField(workflow, "id", ID);
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        when(workflows.saveAndFlush(workflow)).thenReturn(workflow);
        when(documents.getDocument(OWNER, "doc-1")).thenReturn(new ObjectMapper().readTree(
                "{\"owner_user_id\":\"73\",\"current_version\":1,\"pending_version\":1}"));

        var submitted = service.submit(OWNER, Set.of("DOCUMENT_SUBMIT"), ID);
        assertThat(submitted.status()).isEqualTo(DocumentWorkflowStatus.PENDING_STAFF_REVIEW);
        assertThat(submitted.submittedDocumentVersion()).isEqualTo(1);

        assertThatThrownBy(() -> service.submit(OWNER, Set.of("DOCUMENT_SUBMIT"), ID))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(409));
        verify(audit).save(any(DocumentWorkflowAudit.class));
    }

    @Test
    void staffClaimIsExclusiveAndCannotBeRepeatedAfterClaim() {
        DocumentWorkflow workflow = submittedWorkflow();
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        when(workflows.saveAndFlush(workflow)).thenReturn(workflow);

        var claimed = service.claim(REVIEWER, Set.of("ROLE_STAFF", "DOCUMENT_CLAIM"), ID);
        assertThat(claimed.status()).isEqualTo(DocumentWorkflowStatus.STAFF_REVIEWING);
        assertThat(claimed.reviewerUserId()).isEqualTo(REVIEWER);

        assertThatThrownBy(() -> service.claim("82", Set.of("ROLE_STAFF", "DOCUMENT_CLAIM"), ID))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(409));
        verify(workflows, org.mockito.Mockito.times(2)).lockById(ID);
    }

    @Test
    void assignedStaffCanReleaseClaimAndAnotherStaffCanClaimIt() {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        when(workflows.saveAndFlush(workflow)).thenReturn(workflow);

        assertThatThrownBy(() -> service.release("82", Set.of("ROLE_STAFF", "DOCUMENT_RELEASE"), ID))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(403));

        var released = service.release(REVIEWER, Set.of("ROLE_STAFF", "DOCUMENT_RELEASE"), ID);
        assertThat(released.status()).isEqualTo(DocumentWorkflowStatus.PENDING_STAFF_REVIEW);
        assertThat(released.reviewerUserId()).isNull();
        assertThatThrownBy(() -> service.release("82", Set.of("ROLE_STAFF", "DOCUMENT_RELEASE"), ID))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(409));

        var reclaimed = service.claim("82", Set.of("ROLE_STAFF", "DOCUMENT_CLAIM"), ID);
        assertThat(reclaimed.status()).isEqualTo(DocumentWorkflowStatus.STAFF_REVIEWING);
        assertThat(reclaimed.reviewerUserId()).isEqualTo("82");
        var events = org.mockito.ArgumentCaptor.forClass(DocumentWorkflowAudit.class);
        verify(audit, org.mockito.Mockito.times(2)).save(events.capture());
        assertThat(events.getAllValues().getFirst().getAction()).isEqualTo("STAFF_RELEASE");
        assertThat(events.getAllValues().getFirst().getPreviousReviewerUserId()).isEqualTo(REVIEWER);
        assertThat(events.getAllValues().getFirst().getNewReviewerUserId()).isNull();
    }

    @Test
    void adminCanReassignOnlyToBackendVerifiedStaffAndOldReviewerLosesAccess() {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        when(workflows.saveAndFlush(workflow)).thenReturn(workflow);
        ReassignRequest request = new ReassignRequest(82L, "Transfer due to workload");

        var reassigned = service.reassign("admin-1",
                Set.of("ROLE_ADMINISTRATOR", "DOCUMENT_REASSIGN"), ID, "82", request);
        assertThat(reassigned.status()).isEqualTo(DocumentWorkflowStatus.STAFF_REVIEWING);
        assertThat(reassigned.reviewerUserId()).isEqualTo("82");
        assertThatThrownBy(() -> service.staffReview(REVIEWER,
                Set.of("ROLE_STAFF", "DOCUMENT_REVIEW"), ID,
                new StaffReviewRequest(StaffReviewResult.PASSED, null)))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(403));
        var passed = service.staffReview("82", Set.of("ROLE_STAFF", "DOCUMENT_REVIEW"), ID,
                new StaffReviewRequest(StaffReviewResult.PASSED, "Reviewed"));
        assertThat(passed.status()).isEqualTo(DocumentWorkflowStatus.PENDING_MANAGER_APPROVAL);

        var events = org.mockito.ArgumentCaptor.forClass(DocumentWorkflowAudit.class);
        verify(audit, org.mockito.Mockito.times(2)).save(events.capture());
        DocumentWorkflowAudit reassignEvent = events.getAllValues().getFirst();
        assertThat(reassignEvent.getAction()).isEqualTo("STAFF_REASSIGN");
        assertThat(reassignEvent.getActorUserId()).isEqualTo("admin-1");
        assertThat(reassignEvent.getPreviousReviewerUserId()).isEqualTo(REVIEWER);
        assertThat(reassignEvent.getNewReviewerUserId()).isEqualTo("82");
        assertThat(reassignEvent.getComment()).isEqualTo("Transfer due to workload");
    }

    @Test
    void reassignRejectsUnverifiedTargetsWrongRolesAndInvalidStates() {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        ReassignRequest request = new ReassignRequest(82L, "Transfer due to workload");

        assertThatThrownBy(() -> service.reassign("admin-1",
                Set.of("ROLE_ADMINISTRATOR", "DOCUMENT_REASSIGN"), ID, "83", request))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(403));
        assertThatThrownBy(() -> service.reassign("manager-1",
                Set.of("ROLE_MANAGER", "DOCUMENT_REASSIGN"), ID, "82", request))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(403));
        assertThatThrownBy(() -> service.reassign(REVIEWER,
                Set.of("ROLE_STAFF", "DOCUMENT_REVIEW"), ID, "82", request))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(403));

        workflow.review(StaffReviewResult.PASSED, "Passed");
        assertThatThrownBy(() -> service.reassign("admin-1",
                Set.of("ROLE_ADMIN", "DOCUMENT_REASSIGN"), ID, "82", request))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(409));
        verify(audit, never()).save(any());
    }

    @Test
    void releaseAndReviewInterleavingAllowsOnlyTheFirstValidTransition() {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        when(workflows.saveAndFlush(workflow)).thenReturn(workflow);

        service.release(REVIEWER, Set.of("ROLE_STAFF", "DOCUMENT_RELEASE"), ID);
        assertThatThrownBy(() -> service.staffReview(REVIEWER,
                Set.of("ROLE_STAFF", "DOCUMENT_REVIEW"), ID,
                new StaffReviewRequest(StaffReviewResult.PASSED, "Reviewed")))
                .isInstanceOf(ApiException.class);
        verify(audit).save(any(DocumentWorkflowAudit.class));
    }

    @Test
    void optimisticLockConflictDoesNotWriteAudit() {
        when(workflows.lockById(ID)).thenThrow(
                new org.springframework.orm.ObjectOptimisticLockingFailureException(DocumentWorkflow.class, ID));

        assertThatThrownBy(() -> service.claim(REVIEWER, Set.of("ROLE_STAFF", "DOCUMENT_CLAIM"), ID))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(409));
        verify(audit, never()).save(any());
    }

    @Test
    void staffCanRequestChangesOwnerCanEditAndResubmitNewVersion() throws Exception {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        when(workflows.saveAndFlush(workflow)).thenReturn(workflow);
        when(documents.getDocument(OWNER, "doc-1")).thenReturn(
                new ObjectMapper().readTree("{\"owner_user_id\":\"73\",\"current_version\":0,\"pending_version\":1}"),
                new ObjectMapper().readTree("{\"owner_user_id\":\"73\",\"current_version\":0,\"pending_version\":2}"));

        var changes = service.staffReview(REVIEWER, Set.of("ROLE_STAFF", "DOCUMENT_REVIEW"), ID,
                new StaffReviewRequest(StaffReviewResult.CHANGES_REQUESTED, "Please clarify the setup steps"));
        assertThat(changes.status()).isEqualTo(DocumentWorkflowStatus.CHANGES_REQUESTED);

        var edited = service.editAfterChanges(OWNER, Set.of("DOCUMENT_UPDATE"), ID,
                new com.livingdocs.github.dto.WorkflowDtos.EditDocumentRequest("# Updated", "Clarified setup"));
        assertThat(edited.status()).isEqualTo(DocumentWorkflowStatus.CHANGES_REQUESTED);
        verify(documents).editOwnedDocument(OWNER, "doc-1", 1, "# Updated", "Clarified setup");

        var resubmitted = service.submit(OWNER, Set.of("DOCUMENT_SUBMIT"), ID);
        assertThat(resubmitted.status()).isEqualTo(DocumentWorkflowStatus.PENDING_STAFF_REVIEW);
        assertThat(resubmitted.submittedDocumentVersion()).isEqualTo(2);
        verify(audit, org.mockito.Mockito.times(3)).save(any(DocumentWorkflowAudit.class));
    }

    @Test
    void managerCanRejectOnlyAfterStaffPassAndRejectionIsAudited() throws Exception {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        workflow.review(StaffReviewResult.PASSED, "Checks passed");
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        when(workflows.saveAndFlush(workflow)).thenReturn(workflow);
        when(documents.getDocument(MANAGER, "doc-1")).thenReturn(new ObjectMapper().readTree(
                "{\"owner_user_id\":\"73\",\"current_version\":0,\"pending_version\":1,\"versions_total\":1}"));

        var rejected = service.decide(MANAGER, Set.of("ROLE_MANAGER", "DOCUMENT_REJECT"), ID,
                ManagerDecision.REJECTED, "Does not meet the documentation standard");

        assertThat(rejected.status()).isEqualTo(DocumentWorkflowStatus.REJECTED);
        verify(documents).resolveDocumentVersion(MANAGER, OWNER, "doc-1", 1, "REJECTED",
                "Does not meet the documentation standard");
        verify(audit).save(any(DocumentWorkflowAudit.class));
    }

    @Test
    void ownerAndRolePermissionsAreRequiredToReadOrAct() {
        DocumentWorkflow workflow = submittedWorkflow();
        when(workflows.findById(ID)).thenReturn(Optional.of(workflow));
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));

        assertThatThrownBy(() -> service.get("999", Set.of("DOCUMENT_VIEW"), ID))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(404));
        assertThatThrownBy(() -> service.claim("82", Set.of("ROLE_MANAGER", "DOCUMENT_CLAIM"), ID))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(403));
        assertThatThrownBy(() -> service.staffReview("82", Set.of("ROLE_MANAGER", "DOCUMENT_REVIEW"), ID,
                new StaffReviewRequest(StaffReviewResult.PASSED, null)))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(403));
        assertThatThrownBy(() -> service.staffReview("82",
                Set.of("ROLE_ADMINISTRATOR", "DOCUMENT_REVIEW"), ID,
                new StaffReviewRequest(StaffReviewResult.PASSED, null)))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(403));
        assertThatThrownBy(() -> service.decide("admin-1",
                Set.of("ROLE_ADMINISTRATOR", "DOCUMENT_APPROVE"), ID,
                ManagerDecision.APPROVED, null))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(403));
        assertThatThrownBy(() -> service.decide("dev-1",
                Set.of("ROLE_DEVELOPER", "DOCUMENT_APPROVE"), ID,
                ManagerDecision.APPROVED, null))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(403));
        assertThatThrownBy(() -> service.submit(OWNER, Set.of(), ID))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(403));
    }
    @Test
    void managerCanReadEvidenceForTheExactSubmittedVersion() throws Exception {
    DocumentWorkflow workflow = pendingStaffWorkflow();
    workflow.review(StaffReviewResult.PASSED, "All checks passed");

    when(workflows.findById(ID)).thenReturn(Optional.of(workflow));
    when(documents.getDocument(MANAGER, "doc-1")).thenReturn(
            new ObjectMapper().readTree(
                    "{\"id\":\"doc-1\",\"owner_user_id\":\"73\","
                    + "\"current_version\":0,\"pending_version\":1}"));

    var expectedEvidence = new ObjectMapper().readTree(
            "{\"job_id\":\"job-1\",\"files\":[]}");

    when(documents.getDocumentEvidence(MANAGER, "doc-1", 1))
            .thenReturn(expectedEvidence);

    var result = service.evidence(
            MANAGER,
            Set.of("ROLE_MANAGER", "DOCUMENT_APPROVAL_QUEUE_VIEW"),
            ID);

    assertThat(result).isEqualTo(expectedEvidence);

    verify(documents).getDocumentEvidence(MANAGER, "doc-1", 1);
}

@Test
void managerCannotReadEvidenceBeforeStaffReviewPasses() {
    DocumentWorkflow workflow = pendingStaffWorkflow();

    when(workflows.findById(ID)).thenReturn(Optional.of(workflow));

    assertThatThrownBy(() -> service.evidence(
            MANAGER,
            Set.of("ROLE_MANAGER", "DOCUMENT_APPROVAL_QUEUE_VIEW"),
            ID))
            .isInstanceOf(ApiException.class);

    verify(documents, never()).getDocumentEvidence(
            any(), any(), org.mockito.ArgumentMatchers.anyInt());
}

@Test
void nonManagerCannotReadGroundingEvidence() {
    assertThatThrownBy(() -> service.evidence(
            MANAGER,
            Set.of("DOCUMENT_APPROVAL_QUEUE_VIEW"),
            ID))
            .isInstanceOf(ApiException.class)
            .satisfies(error -> assertThat(
                    ((ApiException) error).getStatus().value()).isEqualTo(403));

    verify(workflows, never()).findById(ID);
}
    @Test
    void historyIsReturnedOnlyToAuthorizedOwner() {
        DocumentWorkflow workflow = submittedWorkflow();
        when(workflows.findById(ID)).thenReturn(Optional.of(workflow));
        when(audit.findByWorkflowIdOrderByCreatedAtAsc(ID)).thenReturn(List.of(
                new DocumentWorkflowAudit(ID, OWNER, "SUBMITTED", "DRAFT", "PENDING_STAFF_REVIEW", null)));

        assertThat(service.history(OWNER, Set.of("DOCUMENT_VIEW"), ID)).hasSize(1);
        assertThatThrownBy(() -> service.history("999", Set.of("DOCUMENT_VIEW"), ID))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(404));
    }
     @Test
void managerCanReadAuditTrailForPendingApprovalWorkflow() {
    DocumentWorkflow workflow = pendingStaffWorkflow();
    workflow.review(StaffReviewResult.PASSED, "All checks passed");

    when(workflows.findById(ID)).thenReturn(Optional.of(workflow));
    when(audit.findByWorkflowIdOrderByCreatedAtAsc(ID)).thenReturn(List.of(
            new DocumentWorkflowAudit(
                    ID,
                    REVIEWER,
                    "PASSED",
                    "STAFF_REVIEWING",
                    "PENDING_MANAGER_APPROVAL",
                    "All checks passed"
            ),
            new DocumentWorkflowAudit(
                    ID,
                    MANAGER,
                    "APPROVED",
                    "PENDING_MANAGER_APPROVAL",
                    "APPROVED",
                    "Approved"
            )
    ));

    var history = service.history(
            MANAGER,
            Set.of("ROLE_MANAGER", "DOCUMENT_APPROVAL_QUEUE_VIEW"),
            ID
    );

    assertThat(history).hasSize(2);
    verify(audit).findByWorkflowIdOrderByCreatedAtAsc(ID);
}
        @Test
    void managerCanRollbackApprovedDocumentAndRollbackMustPassStaffReviewAgain() throws Exception {
        DocumentWorkflow workflow = approvedWorkflow();

        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));

        when(documents.getDocument(MANAGER, "doc-1")).thenReturn(
                new ObjectMapper().readTree(
                        "{\"owner_user_id\":\"73\",\"current_version\":2,\"pending_version\":null}"
                )
        );

        when(documents.rollbackDocumentVersion(
                MANAGER,
                OWNER,
                "doc-1",
                1,
                "Restore stable version"
        )).thenReturn(
                new ObjectMapper().readTree(
                        "{\"number\":3,\"status\":\"proposed\",\"origin\":\"rollback\",\"restored_from\":1}"
                )
        );

        when(workflows.saveAndFlush(workflow)).thenReturn(workflow);

        var result = service.rollback(
                MANAGER,
                Set.of("ROLE_MANAGER", "DOCUMENT_ROLLBACK"),
                ID,
                1,
                "Restore stable version"
        );

        assertThat(result.status()).isEqualTo(DocumentWorkflowStatus.PENDING_STAFF_REVIEW);
        assertThat(result.submittedDocumentVersion()).isEqualTo(3);

        verify(documents).rollbackDocumentVersion(
                MANAGER,
                OWNER,
                "doc-1",
                1,
                "Restore stable version"
        );

        verify(workflows).saveAndFlush(workflow);
        verify(audit).save(any(DocumentWorkflowAudit.class));
    }
    @Test
    void persistenceDeclaresUniqueDocumentKeyAndPessimisticClaimDecisionLock() throws Exception {
        Lock lock = DocumentWorkflowRepository.class.getMethod("lockById", UUID.class).getAnnotation(Lock.class);
        Field version = DocumentWorkflow.class.getDeclaredField("optimisticVersion");

        assertThat(lock).isNotNull();
        assertThat(lock.value()).isEqualTo(jakarta.persistence.LockModeType.PESSIMISTIC_WRITE);
        assertThat(version.isAnnotationPresent(jakarta.persistence.Version.class)).isTrue();
        assertThat(DocumentWorkflow.class.getDeclaredField("documentId")
                .getAnnotation(jakarta.persistence.Column.class).unique()).isTrue();
    }
    private static DocumentWorkflow approvedWorkflow() {
    DocumentWorkflow workflow = new DocumentWorkflow("doc-1", "Document", OWNER);
    ReflectionTestUtils.setField(workflow, "id", ID);

    workflow.submit(2);
    workflow.claim(REVIEWER);
    workflow.review(StaffReviewResult.PASSED, "Staff review passed");
    workflow.decide(MANAGER, ManagerDecision.APPROVED, "Approved");

    return workflow;
}
    private static DocumentWorkflow pendingStaffWorkflow() {
        DocumentWorkflow workflow = submittedWorkflow();
        workflow.claim(REVIEWER);
        return workflow;
    }

    private static DocumentWorkflow submittedWorkflow() {
        DocumentWorkflow workflow = new DocumentWorkflow("doc-1", "Document", OWNER);
        ReflectionTestUtils.setField(workflow, "id", ID);
        workflow.submit(1);
        return workflow;
    }
}
