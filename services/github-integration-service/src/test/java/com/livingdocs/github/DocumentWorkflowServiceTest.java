package com.livingdocs.github;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
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
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.ArgumentCaptor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.data.jpa.repository.Lock;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.change.SourceChangeRequest;
import com.livingdocs.github.dto.WorkflowDtos.StaffReviewRequest;
import com.livingdocs.github.dto.WorkflowDtos.ReassignRequest;
import com.livingdocs.github.entity.DocumentWorkflow;
import com.livingdocs.github.entity.DocumentWorkflowAudit;
import com.livingdocs.github.entity.DocumentWorkflowStatus;
import com.livingdocs.github.entity.ManagerDecision;
import com.livingdocs.github.entity.SourceChange;
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
    void independentCommentsKeepReviewOpenAndPreserveSubmittedVersion() {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        workflow.claim(REVIEWER);
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        when(audit.saveAndFlush(any())).thenAnswer(invocation -> invocation.getArgument(0));

        var result = service.addComment(REVIEWER, Set.of("ROLE_STAFF", "DOCUMENT_REVIEW"), ID,
                new com.livingdocs.github.dto.WorkflowDtos.ReviewCommentRequest(" Clarify setup ", 1));

        assertThat(result.comment()).isEqualTo("Clarify setup");
        assertThat(result.documentVersion()).isEqualTo(1);
        assertThat(workflow.getStatus()).isEqualTo(DocumentWorkflowStatus.STAFF_REVIEWING);
        assertThat(workflow.getStaffReviewResult()).isNull();
        verify(workflows, never()).saveAndFlush(any());
    }

    @Test
    void sectionFeedbackUsesExactOffsetsAndSurvivesNewDocumentVersions() {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        when(workflows.findById(ID)).thenReturn(Optional.of(workflow));
        when(documents.getDocumentContent(REVIEWER, "doc-1", 1)).thenReturn("Setup\nSetup");
        when(audit.saveAndFlush(any())).thenAnswer(invocation -> invocation.getArgument(0));
        var section = new com.livingdocs.github.dto.WorkflowDtos.SectionFeedback(6, 11, "Setup");
        var response = service.addComment(REVIEWER, Set.of("ROLE_STAFF", "DOCUMENT_REVIEW"), ID,
                new com.livingdocs.github.dto.WorkflowDtos.ReviewCommentRequest("Explain this section", 1, section));
        assertThat(response.section()).isEqualTo(section);
        var saved = org.mockito.ArgumentCaptor.forClass(DocumentWorkflowAudit.class);
        verify(audit).saveAndFlush(saved.capture());
        when(audit.findByWorkflowIdOrderByCreatedAtAsc(ID)).thenReturn(List.of(saved.getValue()));
        workflow.submit(2);
        var comments = service.comments(OWNER, Set.of("DOCUMENT_VIEW"), ID);
        assertThat(comments).singleElement().satisfies(comment -> {
            assertThat(comment.documentVersion()).isEqualTo(1);
            assertThat(comment.section()).isEqualTo(section);
        });
    }

    @Test
    void sectionFeedbackRejectsInvalidRangesAndQuotes() {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        when(documents.getDocumentContent(REVIEWER, "doc-1", 1)).thenReturn("Setup");
        for (var section : List.of(
                new com.livingdocs.github.dto.WorkflowDtos.SectionFeedback(0, 10, "Setup"),
                new com.livingdocs.github.dto.WorkflowDtos.SectionFeedback(3, 2, "up"),
                new com.livingdocs.github.dto.WorkflowDtos.SectionFeedback(0, 5, "Other"),
                new com.livingdocs.github.dto.WorkflowDtos.SectionFeedback(-1, 5, "Setup"))) {
            assertThatThrownBy(() -> service.addComment(REVIEWER, Set.of("ROLE_STAFF", "DOCUMENT_REVIEW"), ID,
                    new com.livingdocs.github.dto.WorkflowDtos.ReviewCommentRequest("Feedback", 1, section)))
                    .isInstanceOf(ApiException.class);
        }
        verify(audit, never()).saveAndFlush(any());
    }

    @Test
    void independentCommentsRejectOtherReviewersAndStaleVersions() {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        workflow.claim(REVIEWER);
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        var request = new com.livingdocs.github.dto.WorkflowDtos.ReviewCommentRequest("Clarify setup", 1);
        assertThatThrownBy(() -> service.addComment("99",
                Set.of("ROLE_STAFF", "DOCUMENT_REVIEW"), ID, request))
                .isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> service.addComment(REVIEWER,
                Set.of("ROLE_STAFF", "DOCUMENT_REVIEW"), ID,
                new com.livingdocs.github.dto.WorkflowDtos.ReviewCommentRequest("Stale", 2)))
                .isInstanceOf(ApiException.class);
        verify(audit, never()).saveAndFlush(any());
    }

    @Test
    void commentHistoryRemainsReadableToOwnerAfterResubmission() {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        DocumentWorkflowAudit entry = new DocumentWorkflowAudit(ID, REVIEWER,
                "REVIEW_COMMENT", "STAFF_REVIEWING", "STAFF_REVIEWING", "Clarify setup");
        entry.setDocumentVersion(1);
        workflow.submit(2);
        when(workflows.findById(ID)).thenReturn(Optional.of(workflow));
        when(audit.findByWorkflowIdOrderByCreatedAtAsc(ID)).thenReturn(List.of(entry));
        assertThat(service.comments(OWNER, Set.of("DOCUMENT_VIEW"), ID))
                .singleElement().satisfies(comment -> assertThat(comment.documentVersion()).isEqualTo(1));
        assertThatThrownBy(() -> service.comments("99", Set.of("DOCUMENT_VIEW"), ID))
                .isInstanceOf(ApiException.class);
    }

    @Test
    void changeRequestsKeepVersionedFeedbackAcrossReviewRoundsAndLegacyHistory() {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        when(workflows.findById(ID)).thenReturn(Optional.of(workflow));
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        var firstComment = new DocumentWorkflowAudit(ID, REVIEWER, "REVIEW_COMMENT",
                "STAFF_REVIEWING", "STAFF_REVIEWING", "Clarify setup");
        firstComment.setDocumentVersion(1);
        var legacy = new DocumentWorkflowAudit(ID, REVIEWER, "CHANGES_REQUESTED",
                "STAFF_REVIEWING", "CHANGES_REQUESTED", "Legacy feedback");

        service.staffReview(REVIEWER, Set.of("ROLE_STAFF", "DOCUMENT_REVIEW"), ID,
                new StaffReviewRequest(StaffReviewResult.CHANGES_REQUESTED, "Fix setup"));
        var captor = org.mockito.ArgumentCaptor.forClass(DocumentWorkflowAudit.class);
        verify(audit).save(captor.capture());
        var firstRequest = captor.getValue();
        assertThat(firstRequest.getDocumentVersion()).isEqualTo(1);
        assertThat(firstRequest.getActorRole()).isEqualTo("STAFF");

        workflow.submit(2);
        workflow.claim(REVIEWER);
        var secondComment = new DocumentWorkflowAudit(ID, REVIEWER, "REVIEW_COMMENT",
                "STAFF_REVIEWING", "STAFF_REVIEWING", "Add an example");
        secondComment.setDocumentVersion(2);
        var secondRequest = new DocumentWorkflowAudit(ID, REVIEWER, "CHANGES_REQUESTED",
                "STAFF_REVIEWING", "CHANGES_REQUESTED", "Fix example");
        secondRequest.setDocumentVersion(2);
        when(audit.findByWorkflowIdOrderByCreatedAtAsc(ID))
                .thenReturn(List.of(legacy, firstComment, firstRequest, secondComment, secondRequest));
        var requests = service.changeRequests(OWNER, Set.of("DOCUMENT_VIEW"), ID);
        assertThat(requests).hasSize(3);
        assertThat(requests.get(0).documentVersion()).isNull();
        assertThat(requests.get(0).relatedComments()).isEmpty();
        assertThat(requests.get(1).relatedComments()).singleElement()
                .satisfies(comment -> assertThat(comment.comment()).isEqualTo("Clarify setup"));
        assertThat(requests.get(2).relatedComments()).singleElement()
                .satisfies(comment -> assertThat(comment.comment()).isEqualTo("Add an example"));
        assertThatThrownBy(() -> service.changeRequests("99", Set.of("DOCUMENT_VIEW"), ID))
                .isInstanceOf(ApiException.class);
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
        verify(audit, never()).save(any());
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
        verify(audit, never()).save(any());
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
        var events = org.mockito.ArgumentCaptor.forClass(DocumentWorkflowAudit.class);
        verify(audit, org.mockito.Mockito.times(2)).save(events.capture());
        DocumentWorkflowAudit approvalEvent = events.getAllValues().get(1);
        assertThat(approvalEvent.getActorUserId()).isEqualTo(MANAGER);
        assertThat(approvalEvent.getActorRole()).isEqualTo("MANAGER");
        assertThat(approvalEvent.getAction()).isEqualTo("APPROVED");
        assertThat(approvalEvent.getPreviousStatus()).isEqualTo("PENDING_MANAGER_APPROVAL");
        assertThat(approvalEvent.getNewStatus()).isEqualTo("APPROVED");
        assertThat(approvalEvent.getComment()).isEqualTo("Approved");
        assertThat(approvalEvent.getCreatedAt()).isNotNull();
        verify(documents).resolveDocumentVersion(MANAGER, "73", "doc-1", 1, "APPROVED", "Approved");
    }

    @Test
    void managerMayApproveWithoutOptionalComment() throws Exception {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        workflow.review(StaffReviewResult.PASSED, "Checks passed");
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        when(workflows.saveAndFlush(workflow)).thenReturn(workflow);
        when(documents.getDocument(MANAGER, "doc-1")).thenReturn(new ObjectMapper().readTree(
                "{\"owner_user_id\":\"73\",\"current_version\":0,\"pending_version\":1,\"versions_total\":1}"));

        service.decide(MANAGER, Set.of("ROLE_MANAGER", "DOCUMENT_APPROVE"), ID,
                ManagerDecision.APPROVED, null);

        var events = org.mockito.ArgumentCaptor.forClass(DocumentWorkflowAudit.class);
        verify(audit).save(events.capture());
        assertThat(events.getValue().getAction()).isEqualTo("APPROVED");
        assertThat(events.getValue().getComment()).isNull();
    }

    @Test
    void managerCannotRejectWithoutReasonOrCreateAuditEvent() {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        workflow.review(StaffReviewResult.PASSED, "Checks passed");
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));

        assertThatThrownBy(() -> service.decide(MANAGER,
                Set.of("ROLE_MANAGER", "DOCUMENT_REJECT"), ID, ManagerDecision.REJECTED, null))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(400));
        verify(audit, never()).save(any());
        verify(documents, never()).getDocument(any(), any());
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
    void newlyGeneratedDocumentCanBeSubmittedForTheFirstTime() throws Exception {
        // LD-402: the AI service creates an owned document with no accepted version yet
        // (current_version 0) and the generated proposal as pending_version 1.
        DocumentWorkflow workflow = new DocumentWorkflow("doc-1", "Document", OWNER);
        ReflectionTestUtils.setField(workflow, "id", ID);
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        when(workflows.saveAndFlush(workflow)).thenReturn(workflow);
        when(documents.getDocument(OWNER, "doc-1")).thenReturn(new ObjectMapper().readTree(
                """
                {"owner_user_id":"73","current_version":0,"pending_version":1,"source_job_id":"job-1",
                 "initial_generation_save":{"job_id":"job-1","version":1,"actor_user_id":"73",
                 "actor_role":"STAFF","saved_at":"2026-01-01T00:00:00Z"}}
                """));
        when(workflows.saveAndFlush(any(DocumentWorkflow.class))).thenReturn(workflow);

        service.create(OWNER, Set.of("DOCUMENT_CREATE", "ROLE_DEVELOPER"), "doc-1");
        var created = ArgumentCaptor.forClass(DocumentWorkflowAudit.class);
        verify(audit, org.mockito.Mockito.times(2)).save(created.capture());
        var generation = created.getAllValues().getFirst();
        assertThat(generation.getDocumentVersion()).isEqualTo(1);
        assertThat(generation.getTriggerSource()).isEqualTo("INITIAL_GENERATION");
        assertThat(generation.getActorUserId()).isEqualTo(OWNER);
        assertThat(generation.getActorRole()).isEqualTo("STAFF");
        assertThat(generation.getCreatedAt()).isEqualTo(java.time.Instant.parse("2026-01-01T00:00:00Z"));
        assertThat(created.getValue().getTriggerSource()).isEqualTo("REVIEW_WORKFLOW");

        var submitted = service.submit(OWNER, Set.of("DOCUMENT_SUBMIT"), ID);

        assertThat(submitted.status()).isEqualTo(DocumentWorkflowStatus.PENDING_STAFF_REVIEW);
        assertThat(submitted.submittedDocumentVersion()).isEqualTo(1);
        verify(workflows, org.mockito.Mockito.times(2)).saveAndFlush(any(DocumentWorkflow.class));
    }

    @Test
    void documentWithoutAnyVersionCannotBeSubmitted() throws Exception {
        DocumentWorkflow workflow = new DocumentWorkflow("doc-1", "Document", OWNER);
        ReflectionTestUtils.setField(workflow, "id", ID);
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        when(documents.getDocument(OWNER, "doc-1")).thenReturn(new ObjectMapper().readTree(
                "{\"owner_user_id\":\"73\",\"current_version\":0,\"pending_version\":null}"));

        assertThatThrownBy(() -> service.submit(OWNER, Set.of("DOCUMENT_SUBMIT"), ID))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(409));
        verify(workflows, never()).saveAndFlush(any());
        assertThat(workflow.getStatus()).isEqualTo(DocumentWorkflowStatus.DRAFT);
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
    void revisionRejectsStaleEditorAndSubmissionVersions() throws Exception {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        workflow.review(StaffReviewResult.CHANGES_REQUESTED, "Clarify setup");
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        when(documents.getDocument(OWNER, "doc-1")).thenReturn(new ObjectMapper().readTree(
                "{\"owner_user_id\":\"73\",\"current_version\":1,\"pending_version\":3}"));
        assertThatThrownBy(() -> service.editAfterChanges(OWNER, Set.of("DOCUMENT_UPDATE"), ID,
                new com.livingdocs.github.dto.WorkflowDtos.EditDocumentRequest("Updated text", "Fix setup", 2)))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(409));
        verify(documents, never()).editOwnedDocument(any(), any(), anyInt(), any(), any(), any());
        assertThatThrownBy(() -> service.submit(OWNER, Set.of("DOCUMENT_SUBMIT"), ID, 2))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(409));
        assertThat(workflow.getStatus()).isEqualTo(DocumentWorkflowStatus.CHANGES_REQUESTED);
        var submitted = service.submit(OWNER, Set.of("DOCUMENT_SUBMIT"), ID, 3);
        assertThat(submitted.id()).isEqualTo(ID);
        assertThat(submitted.submittedDocumentVersion()).isEqualTo(3);
        assertThat(submitted.status()).isEqualTo(DocumentWorkflowStatus.PENDING_STAFF_REVIEW);
    }

    @Test
    void revisionRequiresOwnerPermissionAndChangesRequestedState() {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        var request = new com.livingdocs.github.dto.WorkflowDtos.EditDocumentRequest("Updated text", null, 1);
        assertThatThrownBy(() -> service.editAfterChanges(OWNER, Set.of("DOCUMENT_UPDATE"), ID, request))
                .isInstanceOf(ApiException.class);
        workflow.review(StaffReviewResult.CHANGES_REQUESTED, "Clarify setup");
        assertThatThrownBy(() -> service.editAfterChanges("99", Set.of("DOCUMENT_UPDATE"), ID, request))
                .isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> service.editAfterChanges(OWNER, Set.of(), ID, request))
                .isInstanceOf(ApiException.class);
        verify(documents, never()).editOwnedDocument(any(), any(), anyInt(), any(), any(), any());
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

        when(documents.editOwnedDocument(OWNER, "doc-1", 1, "# Updated", "Clarified setup", null))
                .thenReturn(new ObjectMapper().readTree("{\"number\":2,\"status\":\"proposed\",\"origin\":\"edit\",\"owner_edit_from\":1,\"created_by\":\"73\",\"saved_actor_role\":\"DEVELOPER\",\"created_at\":\"2026-01-01T00:00:00Z\",\"content\":\"# Updated\",\"note\":\"Clarified setup\"}"));
        var edited = service.editAfterChanges(OWNER, Set.of("DOCUMENT_UPDATE"), ID,
                new com.livingdocs.github.dto.WorkflowDtos.EditDocumentRequest("# Updated", "Clarified setup"));
        assertThat(edited.status()).isEqualTo(DocumentWorkflowStatus.CHANGES_REQUESTED);
        verify(documents).editOwnedDocument(OWNER, "doc-1", 1, "# Updated", "Clarified setup", null);

        var resubmitted = service.submit(OWNER, Set.of("DOCUMENT_SUBMIT"), ID);
        assertThat(resubmitted.status()).isEqualTo(DocumentWorkflowStatus.PENDING_STAFF_REVIEW);
        assertThat(resubmitted.submittedDocumentVersion()).isEqualTo(2);
        verify(audit, org.mockito.Mockito.times(3)).save(any(DocumentWorkflowAudit.class));
    }

    @ParameterizedTest
    @ValueSource(booleans = {false, true})
    void recoversOwnerEditAfterLostResponseOrAuditFailure(boolean auditFailure) throws Exception {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        workflow.review(StaffReviewResult.CHANGES_REQUESTED, "Clarify setup");
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        var mapper = new ObjectMapper();
        var document = mapper.createObjectNode().put("owner_user_id", OWNER).put("pending_version", 1);
        var saved = mapper.readTree("{\"number\":2,\"status\":\"proposed\",\"origin\":\"edit\",\"owner_edit_from\":1,\"created_by\":\"73\",\"saved_actor_role\":\"DEVELOPER\",\"created_at\":\"2026-01-01T00:00:00Z\",\"content\":\"# Updated\",\"note\":\"Clarified setup\"}");
        when(documents.getDocument(OWNER, "doc-1")).thenReturn(document);
        when(documents.getExactDocumentVersion(OWNER, "doc-1", 2)).thenReturn(saved);
        when(documents.editOwnedDocument(OWNER, "doc-1", 1, "# Updated", "Clarified setup", "DEVELOPER"))
                .thenAnswer(call -> {
                    document.put("pending_version", 2);
                    if (!auditFailure) {
                        throw new IllegalStateException("Response lost after saving");
                    }
                    return saved;
                });
        if (auditFailure) {
            when(audit.save(any(DocumentWorkflowAudit.class)))
                    .thenThrow(new IllegalStateException("Audit unavailable")).thenAnswer(call -> call.getArgument(0));
        }
        var request = new com.livingdocs.github.dto.WorkflowDtos.EditDocumentRequest("# Updated", "Clarified setup", 1);
        assertThatThrownBy(() -> service.editAfterChanges(OWNER, Set.of("DOCUMENT_UPDATE", "ROLE_DEVELOPER"), ID, request))
                .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> service.editAfterChanges("99", Set.of("DOCUMENT_UPDATE"), ID, request))
                .isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> service.editAfterChanges(OWNER, Set.of(), ID, request))
                .isInstanceOf(ApiException.class);
        var mismatch = new com.livingdocs.github.dto.WorkflowDtos.EditDocumentRequest("# Different", "Clarified setup", 1);
        assertThatThrownBy(() -> service.editAfterChanges(OWNER, Set.of("DOCUMENT_UPDATE"), ID, mismatch))
                .isInstanceOf(ApiException.class);

        service.editAfterChanges(OWNER, Set.of("DOCUMENT_UPDATE", "ROLE_STAFF"), ID, request);
        when(audit.existsByWorkflowIdAndActionAndDocumentVersion(ID, "DOCUMENT_EDITED", 2)).thenReturn(true);
        service.editAfterChanges(OWNER, Set.of("DOCUMENT_UPDATE"), ID, request);
        verify(documents).editOwnedDocument(any(), any(), anyInt(), any(), any(), any());
        var captured = ArgumentCaptor.forClass(DocumentWorkflowAudit.class);
        verify(audit, org.mockito.Mockito.times(auditFailure ? 2 : 1)).save(captured.capture());
        assertThat(captured.getValue().getDocumentVersion()).isEqualTo(2);
        assertThat(captured.getValue().getActorRole()).isEqualTo("DEVELOPER");
        assertThat(captured.getValue().getCreatedAt()).isEqualTo(java.time.Instant.parse("2026-01-01T00:00:00Z"));
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
        var events = org.mockito.ArgumentCaptor.forClass(DocumentWorkflowAudit.class);
        verify(audit).save(events.capture());
        DocumentWorkflowAudit rejectionEvent = events.getValue();
        assertThat(rejectionEvent.getActorUserId()).isEqualTo(MANAGER);
        assertThat(rejectionEvent.getActorRole()).isEqualTo("MANAGER");
        assertThat(rejectionEvent.getAction()).isEqualTo("REJECTED");
        assertThat(rejectionEvent.getPreviousStatus()).isEqualTo("PENDING_MANAGER_APPROVAL");
        assertThat(rejectionEvent.getNewStatus()).isEqualTo("REJECTED");
        assertThat(rejectionEvent.getComment()).isEqualTo("Does not meet the documentation standard");
        assertThat(rejectionEvent.getCreatedAt()).isNotNull();
    }

    @Test
    void committedManagerRetryRepairsAiWithoutCreatingAnotherAuditRow() {
        DocumentWorkflow workflow = pendingStaffWorkflow();
        workflow.review(StaffReviewResult.PASSED, "Checks passed");
        workflow.decide(MANAGER, ManagerDecision.REJECTED, "Original reason");
        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));
        Set<String> permissions = Set.of("ROLE_MANAGER", "DOCUMENT_REJECT");

        assertThatThrownBy(() -> service.decide(MANAGER, permissions, ID,
                ManagerDecision.REJECTED, "Changed reason", 1)).isInstanceOf(ApiException.class);
        service.decide(MANAGER, permissions, ID, ManagerDecision.REJECTED, " Original reason ", 1);

        verify(documents).resolveDocumentVersion(MANAGER, OWNER, "doc-1", 1,
                "REJECTED", "Original reason", true);
        verify(audit, never()).save(any(DocumentWorkflowAudit.class));
        verify(workflows, never()).saveAndFlush(workflow);
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
    void assignedStaffCanViewReviewEvidenceForSubmittedVersion() throws Exception {
        DocumentWorkflow workflow = pendingStaffWorkflow();

        when(workflows.findById(ID)).thenReturn(Optional.of(workflow));

        when(documents.getDocument(REVIEWER, "doc-1")).thenReturn(
                new ObjectMapper().readTree(
                        "{\"id\":\"doc-1\",\"owner_user_id\":\"73\",\"current_version\":1}"));

        var evidence = new ObjectMapper().readTree(
                "{\"job_id\":\"job-1\",\"template_name\":\"Default\",\"files\":[]}");

        when(documents.getDocumentReviewEvidence(REVIEWER, "doc-1", 1))
                .thenReturn(evidence);
        when(documents.verifySourceSnapshot(OWNER, evidence))
                .thenReturn(evidence);

        var result = service.reviewEvidence(
                REVIEWER,
                Set.of("ROLE_STAFF", "DOCUMENT_REVIEW"),
                ID);

        assertThat(result).isEqualTo(evidence);
        verify(documents).verifySourceSnapshot(OWNER, evidence);
        verify(documents).getDocumentReviewEvidence(REVIEWER, "doc-1", 1);
    }

    @Test
    void unassignedStaffCannotViewReviewEvidence() {
        DocumentWorkflow workflow = pendingStaffWorkflow();

        when(workflows.findById(ID)).thenReturn(Optional.of(workflow));

        assertThatThrownBy(() -> service.reviewEvidence(
                "82",
                Set.of("ROLE_STAFF", "DOCUMENT_REVIEW"),
                ID))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(
                        ((ApiException) error).getStatus().value()).isEqualTo(403));

        verify(documents, never()).getDocumentReviewEvidence(any(), any(), any(Integer.class));
    }

    @Test
    void assignedStaffCanViewReviewComparisonForSubmittedVersion() throws Exception {
        DocumentWorkflow workflow = pendingStaffWorkflow();

        when(workflows.findById(ID)).thenReturn(Optional.of(workflow));

        when(documents.getDocument(REVIEWER, "doc-1")).thenReturn(
                new ObjectMapper().readTree(
                        "{\"id\":\"doc-1\",\"owner_user_id\":\"73\",\"current_version\":1}"));

        var comparison = new ObjectMapper().readTree(
                "{\"pending_version\":{\"number\":1},\"changes\":[]}");

        when(documents.getDocumentReviewComparison(REVIEWER, "doc-1"))
                .thenReturn(comparison);

        var result = service.reviewComparison(
                REVIEWER,
                Set.of("ROLE_STAFF", "DOCUMENT_REVIEW"),
                ID);

        assertThat(result).isEqualTo(comparison);
        verify(documents).getDocumentReviewComparison(REVIEWER, "doc-1");
    }

    @Test
    void ownerCanListAndCompareAnyTwoVersionsOfTheirDocument() throws Exception {
        // LD-183 / LD-184: the owner of a draft compares version 1 with version 3.
        DocumentWorkflow workflow = new DocumentWorkflow("doc-1", "Document", OWNER);
        ReflectionTestUtils.setField(workflow, "id", ID);
        when(workflows.findById(ID)).thenReturn(Optional.of(workflow));
        when(documents.getDocument(OWNER, "doc-1")).thenReturn(new ObjectMapper().readTree(
                "{\"id\":\"doc-1\",\"owner_user_id\":\"73\",\"current_version\":0,\"pending_version\":3}"));
        var versions = new ObjectMapper().readTree("[{\"number\":3},{\"number\":2},{\"number\":1}]");
        var diff = new ObjectMapper().readTree(
                "{\"from_version\":{\"number\":1},\"to_version\":{\"number\":3},\"rows\":[]}");
        when(documents.getDocumentVersions(OWNER, "doc-1")).thenReturn(versions);
        when(documents.compareDocumentVersions(OWNER, "doc-1", 1, 3)).thenReturn(diff);
        Set<String> owner = Set.of("ROLE_DEVELOPER", "DOCUMENT_VIEW");

        assertThat(service.versions(OWNER, owner, ID)).isEqualTo(versions);
        assertThat(service.compareVersions(OWNER, owner, ID, 1, 3)).isEqualTo(diff);
        verify(documents).compareDocumentVersions(OWNER, "doc-1", 1, 3);
    }

    @Test
    void comparisonDefaultsToCurrentAgainstPreviousAndValidatesTheChoice() throws Exception {
        DocumentWorkflow workflow = new DocumentWorkflow("doc-1", "Document", OWNER);
        ReflectionTestUtils.setField(workflow, "id", ID);
        when(workflows.findById(ID)).thenReturn(Optional.of(workflow));
        when(documents.getDocument(OWNER, "doc-1")).thenReturn(new ObjectMapper().readTree(
                "{\"id\":\"doc-1\",\"owner_user_id\":\"73\",\"current_version\":2}"));
        var diff = new ObjectMapper().readTree("{\"rows\":[]}");
        when(documents.compareDocumentVersions(OWNER, "doc-1", null, null)).thenReturn(diff);
        Set<String> owner = Set.of("ROLE_DEVELOPER", "DOCUMENT_VIEW");

        assertThat(service.compareVersions(OWNER, owner, ID, null, null)).isEqualTo(diff);
        assertThatThrownBy(() -> service.compareVersions(OWNER, owner, ID, 2, 2))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> {
                    assertThat(((ApiException) error).getStatus().value()).isEqualTo(400);
                    assertThat(((ApiException) error).getCode()).isEqualTo("DOCUMENT_COMPARISON_INVALID");
                });
        assertThatThrownBy(() -> service.compareVersions(OWNER, owner, ID, 0, 2))
                .isInstanceOf(ApiException.class);
        verify(documents, never()).compareDocumentVersions(OWNER, "doc-1", 2, 2);
    }

    @Test
    void userWhoCannotReadTheWorkflowCannotCompareItsVersions() {
        DocumentWorkflow workflow = new DocumentWorkflow("doc-1", "Document", OWNER);
        ReflectionTestUtils.setField(workflow, "id", ID);
        when(workflows.findById(ID)).thenReturn(Optional.of(workflow));

        assertThatThrownBy(() -> service.compareVersions("99", Set.of("ROLE_DEVELOPER", "DOCUMENT_VIEW"), ID, 1, 2))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(404));
        assertThatThrownBy(() -> service.versions("99", Set.of("ROLE_DEVELOPER", "DOCUMENT_VIEW"), ID))
                .isInstanceOf(ApiException.class);
        verify(documents, never()).getDocument(any(), any());
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
    void staffCannotViewReviewComparisonWhenPendingVersionDiffersFromSubmittedVersion()
            throws Exception {
        DocumentWorkflow workflow = pendingStaffWorkflow();

        when(workflows.findById(ID)).thenReturn(Optional.of(workflow));

        when(documents.getDocument(REVIEWER, "doc-1")).thenReturn(
                new ObjectMapper().readTree(
                        "{\"id\":\"doc-1\",\"owner_user_id\":\"73\",\"current_version\":1}"));

        var comparison = new ObjectMapper().readTree(
                "{\"pending_version\":{\"number\":2},\"changes\":[]}");

        when(documents.getDocumentReviewComparison(REVIEWER, "doc-1"))
                .thenReturn(comparison);

        assertThatThrownBy(() -> service.reviewComparison(
                REVIEWER,
                Set.of("ROLE_STAFF", "DOCUMENT_REVIEW"),
                ID))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(
                        ((ApiException) error).getStatus().value()).isEqualTo(409));
    }
@Test
    void historyIsReturnedOnlyToAuthorizedOwner() {
        DocumentWorkflow workflow = submittedWorkflow();
        when(workflows.findById(ID)).thenReturn(Optional.of(workflow));
        when(audit.findByWorkflowIdOrderByCreatedAtAsc(ID)).thenReturn(List.of(
                new DocumentWorkflowAudit(ID, OWNER, "SUBMITTED", "DRAFT", "PENDING_STAFF_REVIEW", null),
                new DocumentWorkflowAudit(ID, MANAGER, "APPROVED", "PENDING_MANAGER_APPROVAL", "APPROVED",
                        "Approved", null, null, "MANAGER")));

        var history = service.history(OWNER, Set.of("DOCUMENT_VIEW"), ID);
        assertThat(history).hasSize(2);
        assertThat(history).extracting(response -> response.action())
                .containsExactly("SUBMITTED", "APPROVED");
        assertThat(history.get(0).actorRole()).isNull();
        assertThat(history.get(1).actorUserId()).isEqualTo(MANAGER);
        assertThat(history.get(1).workflowId()).isEqualTo(ID);
        assertThat(history.get(1).actorRole()).isEqualTo("MANAGER");
        assertThat(history.get(1).previousStatus()).isEqualTo("PENDING_MANAGER_APPROVAL");
        assertThat(history.get(1).newStatus()).isEqualTo("APPROVED");
        assertThat(history.get(1).comment()).isEqualTo("Approved");
        assertThat(history.get(1).createdAt()).isNotNull();
        assertThatThrownBy(() -> service.history(OWNER, Set.of(), ID))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(404));
        assertThatThrownBy(() -> service.history("999", Set.of("DOCUMENT_VIEW"), ID))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(404));
        verify(audit, org.mockito.Mockito.times(1)).findByWorkflowIdOrderByCreatedAtAsc(ID);
    }

@Test
    void historyAccessibleUsesPermissionAuthoritiesAndStablePagination() {
        when(workflows.findHistoryAccessible(any(), org.mockito.ArgumentMatchers.anyBoolean(),
                org.mockito.ArgumentMatchers.anyBoolean(), org.mockito.ArgumentMatchers.anyBoolean(),
                org.mockito.ArgumentMatchers.anyBoolean(), any(), any(), any(), any(Pageable.class)))
                .thenAnswer(invocation -> Page.empty(invocation.getArgument(8)));

        service.historyAccessible(OWNER, Set.of("ROLE_DEVELOPER", "DOCUMENT_VIEW"), 2, 7);
        service.historyAccessible(REVIEWER, Set.of("ROLE_CUSTOM_QUEUE", "DOCUMENT_REVIEW_QUEUE_VIEW"), 0, 20);
        service.historyAccessible("assigned-reviewer", Set.of("ROLE_CUSTOM_REVIEWER", "DOCUMENT_REVIEW"), 0, 20);
        service.historyAccessible(MANAGER, Set.of("ROLE_CUSTOM_MANAGER", "DOCUMENT_APPROVAL_QUEUE_VIEW"), 1, 10);
        service.historyAccessible("multi-authority", Set.of("ROLE_CUSTOM", "DOCUMENT_VIEW",
                "DOCUMENT_APPROVAL_QUEUE_VIEW"), 0, 20);

        verify(workflows).findHistoryAccessible(org.mockito.ArgumentMatchers.eq(OWNER),
                org.mockito.ArgumentMatchers.eq(true), org.mockito.ArgumentMatchers.eq(false),
                org.mockito.ArgumentMatchers.eq(false), org.mockito.ArgumentMatchers.eq(false),
                any(), any(), any(), any(Pageable.class));
        verify(workflows).findHistoryAccessible(org.mockito.ArgumentMatchers.eq(REVIEWER),
                org.mockito.ArgumentMatchers.eq(false), org.mockito.ArgumentMatchers.eq(true),
                org.mockito.ArgumentMatchers.eq(false), org.mockito.ArgumentMatchers.eq(false),
                any(), any(), any(), any(Pageable.class));
        verify(workflows).findHistoryAccessible(org.mockito.ArgumentMatchers.eq("assigned-reviewer"),
                org.mockito.ArgumentMatchers.eq(false), org.mockito.ArgumentMatchers.eq(false),
                org.mockito.ArgumentMatchers.eq(true), org.mockito.ArgumentMatchers.eq(false),
                any(), any(), any(), any(Pageable.class));
        var managerPage = org.mockito.ArgumentCaptor.forClass(Pageable.class);
        verify(workflows).findHistoryAccessible(org.mockito.ArgumentMatchers.eq(MANAGER),
                org.mockito.ArgumentMatchers.eq(false), org.mockito.ArgumentMatchers.eq(false),
                org.mockito.ArgumentMatchers.eq(false), org.mockito.ArgumentMatchers.eq(true),
                any(), any(), any(), managerPage.capture());
        assertThat(managerPage.getValue().getPageNumber()).isEqualTo(1);
        assertThat(managerPage.getValue().getPageSize()).isEqualTo(10);
        assertThat(managerPage.getValue().getSort().getOrderFor("createdAt").getDirection())
                .isEqualTo(Sort.Direction.DESC);
        assertThat(managerPage.getValue().getSort().getOrderFor("id").getDirection())
                .isEqualTo(Sort.Direction.ASC);
        verify(workflows).findHistoryAccessible(org.mockito.ArgumentMatchers.eq("multi-authority"),
                org.mockito.ArgumentMatchers.eq(true), org.mockito.ArgumentMatchers.eq(false),
                org.mockito.ArgumentMatchers.eq(false), org.mockito.ArgumentMatchers.eq(true),
                any(), any(), any(), any(Pageable.class));
    }

    @Test
    void historyAccessibleRejectsMissingPermissionsAndBadPaginationButAllowsCustomRoles() {
        assertThatThrownBy(() -> service.historyAccessible(OWNER, Set.of("ROLE_STAFF"), 0, 20))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(403));
        assertThatThrownBy(() -> service.historyAccessible(MANAGER,
                Set.of("ROLE_MANAGER", "DOCUMENT_APPROVAL_QUEUE_VIEW"), -1, 20))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(400));
        assertThatThrownBy(() -> service.historyAccessible(MANAGER,
                Set.of("ROLE_MANAGER", "DOCUMENT_APPROVAL_QUEUE_VIEW"), 0, 101))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(400));
        verify(workflows, never()).findHistoryAccessible(any(), org.mockito.ArgumentMatchers.anyBoolean(),
                org.mockito.ArgumentMatchers.anyBoolean(), org.mockito.ArgumentMatchers.anyBoolean(),
                org.mockito.ArgumentMatchers.anyBoolean(), any(), any(), any(), any(Pageable.class));
        when(workflows.findHistoryAccessible(any(), org.mockito.ArgumentMatchers.anyBoolean(),
                org.mockito.ArgumentMatchers.anyBoolean(), org.mockito.ArgumentMatchers.anyBoolean(),
                org.mockito.ArgumentMatchers.anyBoolean(), any(), any(), any(), any(Pageable.class)))
                .thenAnswer(invocation -> Page.empty(invocation.getArgument(8)));
        service.historyAccessible(OWNER, Set.of("ROLE_CUSTOM_OWNER", "DOCUMENT_VIEW"), 0, 20);
        verify(workflows).findHistoryAccessible(org.mockito.ArgumentMatchers.eq(OWNER),
                org.mockito.ArgumentMatchers.eq(true), org.mockito.ArgumentMatchers.eq(false),
                org.mockito.ArgumentMatchers.eq(false), org.mockito.ArgumentMatchers.eq(false),
                any(), any(), any(), any(Pageable.class));
    }

    @Test
    void administratorDiscoveryUsesTheSamePermissionsAsHistoryReads() {
        when(workflows.findHistoryAccessible(any(), org.mockito.ArgumentMatchers.anyBoolean(),
                org.mockito.ArgumentMatchers.anyBoolean(), org.mockito.ArgumentMatchers.anyBoolean(),
                org.mockito.ArgumentMatchers.anyBoolean(), any(), any(), any(), any(Pageable.class)))
                .thenAnswer(invocation -> Page.empty(invocation.getArgument(8)));

        service.historyAccessible("legacy-admin", Set.of("ROLE_ADMIN", "DOCUMENT_APPROVAL_QUEUE_VIEW"), 0, 20);

        verify(workflows).findHistoryAccessible(org.mockito.ArgumentMatchers.eq("legacy-admin"),
                org.mockito.ArgumentMatchers.eq(false), org.mockito.ArgumentMatchers.eq(false),
                org.mockito.ArgumentMatchers.eq(false), org.mockito.ArgumentMatchers.eq(true),
                any(), any(), any(), any(Pageable.class));

        assertThatThrownBy(() -> service.historyAccessible("admin-no-permission", Set.of("ROLE_ADMIN"), 0, 20))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(403));
        verify(workflows, never()).findHistoryAccessible(org.mockito.ArgumentMatchers.eq("admin-no-permission"),
                org.mockito.ArgumentMatchers.anyBoolean(),
                org.mockito.ArgumentMatchers.anyBoolean(), org.mockito.ArgumentMatchers.anyBoolean(),
                org.mockito.ArgumentMatchers.anyBoolean(), any(), any(), any(), any(Pageable.class));
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
    @ParameterizedTest
    @EnumSource(SourceChange.Trigger.class)
    void automaticDraftRecordsTheActualVersionAndTriggerOnce(SourceChange.Trigger trigger) throws Exception {
        DocumentWorkflow workflow = approvedWorkflow();
        when(workflows.lockByDocumentId("doc-1")).thenReturn(Optional.of(workflow));
        var mapper = new ObjectMapper();
        var candidate = mapper.readTree("{\"id\":\"doc-1\",\"owner_user_id\":\"73\"}");
        var draft = mapper.readTree("{\"number\":3,\"status\":\"proposed\"}");
        var revision = new SourceChangeRequest(UUID.randomUUID(), trigger, "a".repeat(40),
                trigger == SourceChange.Trigger.PULL_REQUEST ? 17 : null);

        service.submitRevisionDraft(candidate, revision, () -> draft);
        service.submitRevisionDraft(candidate, revision, () -> draft);

        var event = ArgumentCaptor.forClass(DocumentWorkflowAudit.class);
        verify(audit).save(event.capture());
        assertThat(event.getValue().getDocumentVersion()).isEqualTo(3);
        assertThat(event.getValue().getTriggerSource()).isEqualTo(trigger.name());
        assertThat(event.getValue().getActorRole()).isEqualTo("AI");
        assertThat(event.getValue().getCreatedAt()).isNotNull();
        assertThat(workflow.getStatus()).isEqualTo(DocumentWorkflowStatus.PENDING_STAFF_REVIEW);
    }

    @ParameterizedTest
    @ValueSource(ints = {0, 3})
    void managerCanStartOrRecoverRollbackAndSendItToStaffReview(int pendingVersion) throws Exception {
        DocumentWorkflow workflow = approvedWorkflow();

        when(workflows.lockById(ID)).thenReturn(Optional.of(workflow));

        when(documents.getDocument(MANAGER, "doc-1")).thenReturn(
                new ObjectMapper().readTree(
                        "{\"owner_user_id\":\"73\",\"current_version\":2,\"pending_version\":" + pendingVersion + "}"
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
        var event = ArgumentCaptor.forClass(DocumentWorkflowAudit.class);
        verify(audit).save(event.capture());
        assertThat(event.getValue().getDocumentVersion()).isEqualTo(3);
        assertThat(event.getValue().getTriggerSource()).isEqualTo("ROLLBACK");
        assertThat(event.getValue().getActorRole()).isEqualTo("MANAGER");
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
