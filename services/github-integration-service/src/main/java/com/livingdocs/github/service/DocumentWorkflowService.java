package com.livingdocs.github.service;

import java.util.List;
import java.util.Set;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.fasterxml.jackson.databind.JsonNode;
import com.livingdocs.github.dto.WorkflowDtos.AuditResponse;
import com.livingdocs.github.dto.WorkflowDtos.ReviewCommentRequest;
import com.livingdocs.github.dto.WorkflowDtos.SectionFeedback;
import com.livingdocs.github.dto.WorkflowDtos.ChangeRequestResponse;
import com.livingdocs.github.dto.WorkflowDtos.ReviewCommentResponse;
import com.livingdocs.github.dto.WorkflowDtos.ContentResponse;
import com.livingdocs.github.dto.WorkflowDtos.EditDocumentRequest;
import com.livingdocs.github.dto.WorkflowDtos.PageResponse;
import com.livingdocs.github.dto.WorkflowDtos.ReassignRequest;
import com.livingdocs.github.dto.WorkflowDtos.StaffReviewRequest;
import com.livingdocs.github.dto.WorkflowDtos.WorkflowResponse;
import com.livingdocs.github.entity.ChangeTriggerSource;
import com.livingdocs.github.entity.DocumentWorkflow;
import com.livingdocs.github.entity.DocumentWorkflowAudit;
import com.livingdocs.github.entity.DocumentWorkflowStatus;
import com.livingdocs.github.entity.ManagerDecision;
import com.livingdocs.github.entity.StaffReviewResult;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.repository.DocumentWorkflowAuditRepository;
import com.livingdocs.github.repository.DocumentWorkflowRepository;

@Service
public class DocumentWorkflowService {
    private final DocumentWorkflowRepository workflows;
    private final DocumentWorkflowAuditRepository audit;
    private final DocumentationGenerationService documents;
    private final DocumentationChangeLogService changeLogService;

    public DocumentWorkflowService(DocumentWorkflowRepository workflows,
            DocumentWorkflowAuditRepository audit, DocumentationGenerationService documents) {
        this(workflows, audit, documents, null);
    }

    @Autowired
    public DocumentWorkflowService(DocumentWorkflowRepository workflows,
            DocumentWorkflowAuditRepository audit, DocumentationGenerationService documents,
            DocumentationChangeLogService changeLogService) {
        this.workflows = workflows;
        this.audit = audit;
        this.documents = documents;
        this.changeLogService = changeLogService;
    }

    @Transactional
    public WorkflowResponse create(String actor, Set<String> authorities, String documentId) {
        require(authorities, "DOCUMENT_CREATE");
        JsonNode document = documents.getDocument(actor, documentId);
        requireDocumentOwner(document, actor);
        if (workflows.existsByDocumentId(documentId)) {
            throw conflict("This document already has a review workflow.");
        }
        DocumentWorkflow workflow = workflows.saveAndFlush(
                new DocumentWorkflow(documentId, document.path("title").asText("Untitled"), actor));
        record(workflow, actor, "CREATED", null, workflow.getStatus(), null);
        recordTimeline(workflow.getDocumentId(), null, "WORKFLOW_CREATED",
                "Initialized review workflow for \"" + workflow.getDocumentTitle() + "\"",
                actor, authorities, ChangeTriggerSource.REVIEW_WORKFLOW,
                workflow.getStatus().name(), workflow.getId().toString());
        return toResponse(workflow);
    }

    @Transactional(readOnly = true)
    public PageResponse<WorkflowResponse> mine(String actor, Set<String> authorities, int page, int size) {
        require(authorities, "DOCUMENT_VIEW");
        Page<DocumentWorkflow> result = workflows.findByOwnerUserIdOrderByCreatedAtDesc(actor, page(page, size));
        return page(result.map(DocumentWorkflowService::toResponse));
    }

    @Transactional(readOnly = true)
    public PageResponse<WorkflowResponse> historyAccessible(String actor, Set<String> authorities,
            int page, int size) {
        boolean includeOwned = authorities.contains("DOCUMENT_VIEW");
        boolean includeStaffQueue = authorities.contains("DOCUMENT_REVIEW_QUEUE_VIEW");
        boolean includeAssignedReviews = authorities.contains("DOCUMENT_REVIEW");
        boolean includeManagerDecisions = authorities.contains("DOCUMENT_APPROVAL_QUEUE_VIEW");
        if (!includeOwned && !includeStaffQueue && !includeAssignedReviews && !includeManagerDecisions) {
            throw ApiException.forbidden("Missing permission to discover accessible workflow history.");
        }

        PageRequest validated = page(page, size);
        PageRequest stableOrder = PageRequest.of(validated.getPageNumber(), validated.getPageSize(),
                Sort.by(Sort.Order.desc("createdAt"), Sort.Order.asc("id")));
        Page<DocumentWorkflow> result = workflows.findHistoryAccessible(actor, includeOwned,
                includeStaffQueue, includeAssignedReviews, includeManagerDecisions,
                DocumentWorkflowStatus.PENDING_STAFF_REVIEW, DocumentWorkflowStatus.STAFF_REVIEWING,
                List.of(DocumentWorkflowStatus.PENDING_MANAGER_APPROVAL,
                        DocumentWorkflowStatus.APPROVED, DocumentWorkflowStatus.REJECTED), stableOrder);
        return page(result.map(DocumentWorkflowService::toResponse));
    }

    @Transactional(readOnly = true)
    public PageResponse<WorkflowResponse> staffQueue(String actor, Set<String> authorities, int page, int size) {
        require(authorities, "DOCUMENT_REVIEW_QUEUE_VIEW");
        requireRole(authorities, "STAFF");
        Page<DocumentWorkflow> result = workflows.staffQueue(DocumentWorkflowStatus.PENDING_STAFF_REVIEW,
                DocumentWorkflowStatus.STAFF_REVIEWING, actor, page(page, size));
        return page(result.map(DocumentWorkflowService::toResponse));
    }

    @Transactional(readOnly = true)
    public PageResponse<WorkflowResponse> managerQueue(Set<String> authorities, int page, int size) {
        require(authorities, "DOCUMENT_APPROVAL_QUEUE_VIEW");
        requireAnyRole(authorities, "MANAGER");
        Page<DocumentWorkflow> result = workflows.findByStatusOrderBySubmittedAtAsc(
                DocumentWorkflowStatus.PENDING_MANAGER_APPROVAL, page(page, size));
        return page(result.map(DocumentWorkflowService::toResponse));
    }

    @Transactional(readOnly = true)
    public WorkflowResponse get(String actor, Set<String> authorities, UUID workflowId) {
        DocumentWorkflow workflow = find(workflowId);
        requireReadable(workflow, actor, authorities);
        return toResponse(workflow);
    }

    @Transactional(readOnly = true)
    public ContentResponse content(String actor, Set<String> authorities, UUID workflowId) {
        DocumentWorkflow workflow = find(workflowId);
        requireReadable(workflow, actor, authorities);
        JsonNode document = documents.getDocument(actor, workflow.getDocumentId());
        requireDocumentOwner(document, workflow.getOwnerUserId());
        int version = visibleDocumentVersion(workflow, document);
        return new ContentResponse(workflow.getDocumentId(), version,
                documents.getDocumentContent(actor, workflow.getDocumentId(), version));
    }

    @Transactional(readOnly = true)
    public JsonNode reviewEvidence(String actor, Set<String> authorities, UUID workflowId) {
        require(authorities, "DOCUMENT_REVIEW");
        requireRole(authorities, "STAFF");

        DocumentWorkflow workflow = find(workflowId);

        if (workflow.getStatus() != DocumentWorkflowStatus.STAFF_REVIEWING
                || !actor.equals(workflow.getReviewerUserId())) {
            throw ApiException.forbidden(
                    "Only the assigned staff reviewer can view review evidence.");
        }

        JsonNode document = documents.getDocument(actor, workflow.getDocumentId());
        requireDocumentOwner(document, workflow.getOwnerUserId());

        Integer submittedVersion = workflow.getSubmittedDocumentVersion();

        if (submittedVersion == null || submittedVersion < 1) {
            throw conflict("The workflow has no submitted document version.");
        }

        JsonNode evidence = documents.getDocumentReviewEvidence(
                actor, workflow.getDocumentId(), submittedVersion);

        return documents.verifySourceSnapshot(workflow.getOwnerUserId(), evidence);
    }

    @Transactional(readOnly = true)
    public JsonNode reviewComparison(String actor, Set<String> authorities, UUID workflowId) {
        require(authorities, "DOCUMENT_REVIEW");
        requireRole(authorities, "STAFF");

        DocumentWorkflow workflow = find(workflowId);

        if (workflow.getStatus() != DocumentWorkflowStatus.STAFF_REVIEWING
                || !actor.equals(workflow.getReviewerUserId())) {
            throw ApiException.forbidden(
                    "Only the assigned staff reviewer can compare document versions.");
        }

        JsonNode document = documents.getDocument(actor, workflow.getDocumentId());
        requireDocumentOwner(document, workflow.getOwnerUserId());

        Integer submittedVersion = workflow.getSubmittedDocumentVersion();

        if (submittedVersion == null || submittedVersion < 1) {
            throw conflict("The workflow has no submitted document version.");
        }

        JsonNode comparison = documents.getDocumentReviewComparison(
                actor, workflow.getDocumentId());

        int comparedPendingVersion = comparison.path("pending_version")
                .path("number").asInt(-1);

        if (comparedPendingVersion != submittedVersion) {
            throw conflict("The pending document version does not match the submitted workflow version.");
        }

        return comparison;
    }

    @Transactional(readOnly = true)
    public JsonNode evidence(String actor, Set<String> authorities, UUID workflowId) {
        require(authorities, "DOCUMENT_APPROVAL_QUEUE_VIEW");
        requireRole(authorities, "MANAGER");

        DocumentWorkflow workflow = find(workflowId);
        requireReadable(workflow, actor, authorities);

        if (workflow.getStaffReviewResult() != StaffReviewResult.PASSED) {
            throw ApiException.forbidden(
                    "Grounding evidence is available only after a successful staff review.");
        }

        JsonNode document = documents.getDocument(actor, workflow.getDocumentId());
        requireDocumentOwner(document, workflow.getOwnerUserId());

        int version = workflow.getSubmittedDocumentVersion() == null
                ? visibleDocumentVersion(workflow, document)
                : workflow.getSubmittedDocumentVersion();

        return documents.getDocumentEvidence(actor, workflow.getDocumentId(), version);
    }

    @Transactional(readOnly = true)
    public List<AuditResponse> history(String actor, Set<String> authorities, UUID workflowId) {
        DocumentWorkflow workflow = find(workflowId);
        requireReadable(workflow, actor, authorities);
        return audit.findByWorkflowIdOrderByCreatedAtAsc(workflowId).stream()
                .map(e -> new AuditResponse(e.getId(), e.getWorkflowId(), e.getActorUserId(), e.getActorRole(), e.getAction(),
                        e.getPreviousStatus(), e.getNewStatus(), e.getPreviousReviewerUserId(),
                        e.getNewReviewerUserId(), e.getComment(), e.getCreatedAt()))
                .toList();
    }

    @Transactional
    public WorkflowResponse submit(String actor, Set<String> authorities, UUID workflowId) {
        return submit(actor, authorities, workflowId, null);
    }

    @Transactional
    public WorkflowResponse submit(String actor, Set<String> authorities, UUID workflowId, Integer expectedVersion) {
        require(authorities, "DOCUMENT_SUBMIT");
        DocumentWorkflow workflow = lock(workflowId);
        requireOwner(workflow, actor);
        DocumentWorkflowStatus previous = workflow.getStatus();
        if (previous != DocumentWorkflowStatus.DRAFT && previous != DocumentWorkflowStatus.CHANGES_REQUESTED) {
            throw conflict("Only a draft or a changes-requested workflow can be submitted.");
        }
        JsonNode document = documents.getDocument(actor, workflow.getDocumentId());
        requireDocumentOwner(document, actor);
        int version = documentVersionForSubmit(workflow, document);
        if (expectedVersion != null && expectedVersion != version) {
            throw conflict("The document version changed. Reload before submitting.");
        }
        workflow.submit(version);
        workflows.saveAndFlush(workflow);
        record(workflow, actor, "SUBMITTED", previous, workflow.getStatus(), null);
        recordTimeline(workflow.getDocumentId(), version, "SUBMITTED_FOR_REVIEW",
                "Submitted version " + version + " for staff review",
                actor, authorities, ChangeTriggerSource.REVIEW_WORKFLOW,
                workflow.getStatus().name(), workflow.getId().toString());
        return toResponse(workflow);
    }

    @Transactional
    public WorkflowResponse claim(String actor, Set<String> authorities, UUID workflowId) {
        require(authorities, "DOCUMENT_CLAIM");
        requireRole(authorities, "STAFF");
        DocumentWorkflow workflow = lock(workflowId);
        if (workflow.getStatus() != DocumentWorkflowStatus.PENDING_STAFF_REVIEW) {
            throw conflict("Only a document pending staff review can be claimed.");
        }
        DocumentWorkflowStatus previous = workflow.getStatus();
        workflow.claim(actor);
        workflows.saveAndFlush(workflow);
        record(workflow, actor, "CLAIMED", previous, workflow.getStatus(), null, null, actor);
        recordTimeline(workflow.getDocumentId(), workflow.getSubmittedDocumentVersion(), "STAFF_CLAIMED",
                "Staff reviewer claimed version " + workflow.getSubmittedDocumentVersion() + " for review",
                actor, authorities, ChangeTriggerSource.REVIEW_WORKFLOW,
                workflow.getStatus().name(), workflow.getId().toString());
        return toResponse(workflow);
    }

    @Transactional
    public WorkflowResponse release(String actor, Set<String> authorities, UUID workflowId) {
        require(authorities, "DOCUMENT_RELEASE");
        requireRole(authorities, "STAFF");
        DocumentWorkflow workflow = lock(workflowId);
        if (workflow.getStatus() != DocumentWorkflowStatus.STAFF_REVIEWING) {
            throw conflict("Only an active staff review can be released.");
        }
        if (!actor.equals(workflow.getReviewerUserId())) {
            throw ApiException.forbidden("Only the assigned STAFF reviewer can release this claim.");
        }
        DocumentWorkflowStatus previous = workflow.getStatus();
        workflow.releaseClaim();
        workflows.saveAndFlush(workflow);
        record(workflow, actor, "STAFF_RELEASE", previous, workflow.getStatus(), null, actor, null);
        recordTimeline(workflow.getDocumentId(), workflow.getSubmittedDocumentVersion(), "STAFF_RELEASED",
                "Staff reviewer released review claim",
                actor, authorities, ChangeTriggerSource.REVIEW_WORKFLOW,
                workflow.getStatus().name(), workflow.getId().toString());
        return toResponse(workflow);
    }

    @Transactional
    public WorkflowResponse reassign(String actor, Set<String> authorities, UUID workflowId,
            String verifiedStaffUserId, ReassignRequest request) {
        require(authorities, "DOCUMENT_REASSIGN");
        requireAdministrator(authorities);
        String targetId = Long.toString(request.targetStaffUserId());
        if (!targetId.equals(verifiedStaffUserId)) {
            throw ApiException.forbidden("The target STAFF identity was not verified by the backend.");
        }
        DocumentWorkflow workflow = lock(workflowId);
        if (workflow.getStatus() != DocumentWorkflowStatus.STAFF_REVIEWING) {
            throw conflict("Only an active staff review can be reassigned.");
        }
        String previousReviewer = workflow.getReviewerUserId();
        if (targetId.equals(previousReviewer)) {
            throw conflict("The workflow is already assigned to this STAFF member.");
        }
        DocumentWorkflowStatus previous = workflow.getStatus();
        workflow.reassignClaim(targetId);
        workflows.saveAndFlush(workflow);
        record(workflow, actor, "STAFF_REASSIGN", previous, workflow.getStatus(), request.reason(),
                previousReviewer, targetId);
        String reason = normalizeComment(request.reason());
        recordTimeline(workflow.getDocumentId(), workflow.getSubmittedDocumentVersion(), "STAFF_REASSIGNED",
                "Reassigned review from " + previousReviewer + " to " + targetId
                        + (reason != null ? ": " + reason : ""),
                actor, authorities, ChangeTriggerSource.REVIEW_WORKFLOW,
                workflow.getStatus().name(), workflow.getId().toString());
        return toResponse(workflow);
    }

    @Transactional
    public ReviewCommentResponse addComment(String actor, Set<String> authorities, UUID workflowId,
            ReviewCommentRequest request) {
        require(authorities, "DOCUMENT_REVIEW");
        requireRole(authorities, "STAFF");
        DocumentWorkflow workflow = lock(workflowId);
        if (workflow.getStatus() != DocumentWorkflowStatus.STAFF_REVIEWING
                || !actor.equals(workflow.getReviewerUserId())) {
            throw ApiException.forbidden("Only the assigned staff reviewer can comment.");
        }
        if (!request.documentVersion().equals(workflow.getSubmittedDocumentVersion())) {
            throw conflict("The submitted document version changed. Reload before commenting.");
        }
        DocumentWorkflowAudit entry = new DocumentWorkflowAudit(workflowId, actor, "REVIEW_COMMENT",
                workflow.getStatus().name(), workflow.getStatus().name(),
                normalizeComment(request.comment()), null, null, "STAFF");
        entry.setDocumentVersion(workflow.getSubmittedDocumentVersion());
        if (request.section() != null) {
            SectionFeedback section = request.section();
            String content = documents.getDocumentContent(actor, workflow.getDocumentId(),
                    workflow.getSubmittedDocumentVersion());
            if (section.startOffset() < 0 || section.endOffset() <= section.startOffset()
                    || section.endOffset() > content.length()
                    || !content.substring(section.startOffset(), section.endOffset()).equals(section.quote())) {
                throw ApiException.badRequest("The selected passage does not match the submitted document.");
            }
            entry.setSectionFeedback(section.startOffset(), section.endOffset(), section.quote());
        }
        return toCommentResponse(audit.saveAndFlush(entry));
    }

    @Transactional(readOnly = true)
    public List<ReviewCommentResponse> comments(String actor, Set<String> authorities, UUID workflowId) {
        DocumentWorkflow workflow = find(workflowId);
        requireReadable(workflow, actor, authorities);
        return audit.findByWorkflowIdOrderByCreatedAtAsc(workflowId).stream()
                .filter(entry -> "REVIEW_COMMENT".equals(entry.getAction()))
                .map(DocumentWorkflowService::toCommentResponse)
                .toList();
    }

    private static ReviewCommentResponse toCommentResponse(DocumentWorkflowAudit entry) {
        return new ReviewCommentResponse(entry.getId(), entry.getWorkflowId(), entry.getActorUserId(),
                entry.getDocumentVersion(), entry.getComment(), entry.getCreatedAt(),
                entry.getSectionQuote() == null ? null : new SectionFeedback(
                        entry.getSectionStartOffset(), entry.getSectionEndOffset(), entry.getSectionQuote()));
    }

    @Transactional(readOnly = true)
    public List<ChangeRequestResponse> changeRequests(String actor, Set<String> authorities, UUID workflowId) {
        DocumentWorkflow workflow = find(workflowId);
        requireReadable(workflow, actor, authorities);
        List<DocumentWorkflowAudit> history = audit.findByWorkflowIdOrderByCreatedAtAsc(workflowId);
        return history.stream()
                .filter(entry -> "CHANGES_REQUESTED".equals(entry.getAction()))
                .map(request -> new ChangeRequestResponse(request.getId(), request.getActorUserId(),
                        request.getDocumentVersion(), request.getComment(), request.getCreatedAt(),
                        history.stream()
                                .filter(comment -> "REVIEW_COMMENT".equals(comment.getAction()))
                                .filter(comment -> request.getDocumentVersion() != null
                                        && request.getDocumentVersion().equals(comment.getDocumentVersion()))
                                .filter(comment -> !comment.getCreatedAt().isAfter(request.getCreatedAt()))
                                .map(DocumentWorkflowService::toCommentResponse).toList()))
                .toList();
    }

    @Transactional
    public WorkflowResponse staffReview(String actor, Set<String> authorities, UUID workflowId,
            StaffReviewRequest request) {
        require(authorities, "DOCUMENT_REVIEW");
        requireRole(authorities, "STAFF");
        DocumentWorkflow workflow = lock(workflowId);
        if (workflow.getStatus() != DocumentWorkflowStatus.STAFF_REVIEWING
                || !actor.equals(workflow.getReviewerUserId())) {
            throw ApiException.forbidden("Only the assigned staff reviewer can review this document.");
        }
        StaffReviewResult result = request.result();
        if (result == StaffReviewResult.CHANGES_REQUESTED
                && (request.comment() == null || request.comment().isBlank())) {
            throw ApiException.badRequest("A comment is required when requesting changes.");
        }
        DocumentWorkflowStatus previous = workflow.getStatus();
        String comment = normalizeComment(request.comment());
        workflow.review(result, comment);
        workflows.saveAndFlush(workflow);
        record(workflow, actor, result.name(), previous, workflow.getStatus(), request.comment());
        recordTimeline(workflow.getDocumentId(), workflow.getSubmittedDocumentVersion(),
                "STAFF_" + result.name(),
                comment != null ? comment : "Staff review completed: " + result.name(),
                actor, authorities, ChangeTriggerSource.REVIEW_WORKFLOW,
                workflow.getStatus().name(), workflow.getId().toString());
        return toResponse(workflow);
    }

    @Transactional
    public WorkflowResponse editAfterChanges(String actor, Set<String> authorities, UUID workflowId,
            EditDocumentRequest request) {
        require(authorities, "DOCUMENT_UPDATE");
        DocumentWorkflow workflow = lock(workflowId);
        requireOwner(workflow, actor);
        if (workflow.getStatus() != DocumentWorkflowStatus.CHANGES_REQUESTED) {
            throw conflict("A document can only be edited after staff requests changes.");
        }
        String comment = normalizeComment(request.note());
        DocumentWorkflowStatus current = workflow.getStatus();
        JsonNode document = documents.getDocument(actor, workflow.getDocumentId());
        requireDocumentOwner(document, workflow.getOwnerUserId());
        int pendingVersion = document.path("pending_version").asInt(0);
        int expectedVersion = pendingVersion > 0
                ? pendingVersion
                : document.path("current_version").asInt(0);
        if (expectedVersion <= 0) {
            throw conflict("The document has no editable version.");
        }
        JsonNode editedVersion = DocumentationGenerationService.callWithChangeLogOverride(
                authorities, true,
                () -> documents.editOwnedDocument(actor, workflow.getDocumentId(),
                        expectedVersion, request.content(), comment));
        int newVersion = editedVersion != null
                ? editedVersion.path("number").asInt(expectedVersion + 1)
                : expectedVersion + 1;
        if (request.expectedVersion() != null && request.expectedVersion() != expectedVersion) {
            throw conflict("The document version changed. Reload before saving.");
        }
        documents.editOwnedDocument(actor, workflow.getDocumentId(),
                expectedVersion, request.content(), comment);
        record(workflow, actor, "DOCUMENT_EDITED", current, current, comment);
        recordTimeline(workflow.getDocumentId(), newVersion, "CONTENT_UPDATED",
                comment != null ? comment : "Updated documentation content to version " + newVersion,
                actor, authorities, ChangeTriggerSource.MANUAL_EDIT,
                current.name(), workflow.getId().toString());
        return toResponse(workflow);
    }

    @Transactional
    public WorkflowResponse decide(String actor, Set<String> authorities, UUID workflowId,
            ManagerDecision decision, String comment) {
        require(authorities, decision == ManagerDecision.APPROVED ? "DOCUMENT_APPROVE" : "DOCUMENT_REJECT");
        String actorRole = requireRole(authorities, "MANAGER");
        DocumentWorkflow workflow = lock(workflowId);
        if (workflow.getStatus() != DocumentWorkflowStatus.PENDING_MANAGER_APPROVAL
                || workflow.getStaffReviewResult() != StaffReviewResult.PASSED) {
            throw conflict("Manager decisions require a successful staff review.");
        }
        if (actor.equals(workflow.getReviewerUserId())) {
            throw ApiException.forbidden("The staff reviewer cannot make the final manager decision.");
        }
        if (decision == ManagerDecision.REJECTED && (comment == null || comment.isBlank())) {
            throw ApiException.badRequest("A rejection reason is required.");
        }
        DocumentWorkflowStatus previous = workflow.getStatus();
        JsonNode document = documents.getDocument(actor, workflow.getDocumentId());
        requireDocumentOwner(document, workflow.getOwnerUserId());
        int pendingVersion = document.path("pending_version").asInt(0);
        String normalizedComment = normalizeComment(comment);
        if (pendingVersion == workflow.getSubmittedDocumentVersion()) {
            DocumentationGenerationService.runWithChangeLogOverride(authorities, true, () ->
                    documents.resolveDocumentVersion(actor, workflow.getOwnerUserId(), workflow.getDocumentId(),
                            pendingVersion, decision.name(), normalizedComment));
        } else if (pendingVersion == 0) {
            int currentVersion = document.path("current_version").asInt(0);
            int totalVersions = document.path("versions_total").asInt(0);
            boolean approvalAlreadyApplied = decision == ManagerDecision.APPROVED
                    && currentVersion == workflow.getSubmittedDocumentVersion();
            boolean rejectionMayNeedRetry = decision == ManagerDecision.REJECTED
                    && totalVersions >= workflow.getSubmittedDocumentVersion();
            if (rejectionMayNeedRetry) {
                DocumentationGenerationService.runWithChangeLogOverride(authorities, true, () ->
                        documents.resolveDocumentVersion(actor, workflow.getOwnerUserId(), workflow.getDocumentId(),
                                workflow.getSubmittedDocumentVersion(), decision.name(), normalizedComment));
            } else if (!approvalAlreadyApplied) {
                throw conflict("The document version changed during review.");
            }
        } else {
            throw conflict("The document version changed during review.");
        }
        workflow.decide(actor, decision, normalizedComment);
        workflows.saveAndFlush(workflow);
        record(workflow, actor, decision.name(), previous, workflow.getStatus(), comment,
                null, null, actorRole);
        recordTimeline(workflow.getDocumentId(), workflow.getSubmittedDocumentVersion(),
                "MANAGER_" + decision.name(),
                normalizedComment != null ? normalizedComment : "Manager decision: " + decision.name(),
                actor, authorities, ChangeTriggerSource.REVIEW_WORKFLOW,
                workflow.getStatus().name(), workflow.getId().toString());
        return toResponse(workflow);
    }

    @Transactional
    public WorkflowResponse rollback(
            String actor,
            Set<String> authorities,
            UUID workflowId,
            Integer sourceVersion,
            String reason) {

        require(authorities, "DOCUMENT_ROLLBACK");
        requireRole(authorities, "MANAGER");

        DocumentWorkflow workflow = lock(workflowId);

        if (workflow.getStatus() != DocumentWorkflowStatus.APPROVED) {
            throw conflict("Only an approved document can be rolled back.");
        }

        if (sourceVersion == null || sourceVersion <= 0) {
            throw ApiException.badRequest("A valid source version is required.");
        }

        String comment = normalizeComment(reason);

        if (comment == null) {
            throw ApiException.badRequest("A rollback reason is required.");
        }

        if (workflow.getSubmittedDocumentVersion() != null
                && sourceVersion.equals(workflow.getSubmittedDocumentVersion())) {
            throw ApiException.badRequest(
                    "The source version must be different from the currently approved version.");
        }

        JsonNode document = documents.getDocument(actor, workflow.getDocumentId());
        requireDocumentOwner(document, workflow.getOwnerUserId());

        int pendingVersion = document.path("pending_version").asInt(0);
        int currentVersion = document.path("current_version").asInt(0);

        if (pendingVersion != 0
                || currentVersion != workflow.getSubmittedDocumentVersion()) {
            throw conflict("The document version changed. Reload and retry.");
        }

        JsonNode rollbackVersion = DocumentationGenerationService.callWithChangeLogOverride(
                authorities, true,
                () -> documents.rollbackDocumentVersion(
                        actor,
                        workflow.getOwnerUserId(),
                        workflow.getDocumentId(),
                        sourceVersion,
                        comment
                ));

        int newVersion = rollbackVersion != null ? rollbackVersion.path("number").asInt(0) : 0;

        if (newVersion <= 0) {
            throw conflict("The rollback service returned an invalid version.");
        }

        DocumentWorkflowStatus previous = workflow.getStatus();

        workflow.startRollbackReview(newVersion);

        workflows.saveAndFlush(workflow);

        String rollbackSummary = "Restored from version " + sourceVersion + ". Reason: " + comment;
        record(
                workflow,
                actor,
                "ROLLBACK_REQUESTED",
                previous,
                workflow.getStatus(),
                rollbackSummary
        );
        recordTimeline(
                workflow.getDocumentId(),
                newVersion,
                "ROLLED_BACK",
                rollbackSummary,
                actor,
                authorities,
                ChangeTriggerSource.ROLLBACK,
                workflow.getStatus().name(),
                "v" + sourceVersion
        );

        return toResponse(workflow);
    }

    private void recordTimeline(
            String documentId,
            Integer versionNumber,
            String action,
            String summary,
            String actorId,
            Set<String> authorities,
            ChangeTriggerSource triggerSource,
            String status,
            String referenceId
    ) {
        if (changeLogService == null) {
            return;
        }
        changeLogService.recordChange(
                documentId,
                null,
                versionNumber,
                action,
                summary,
                actorId,
                null,
                authorities,
                triggerSource,
                status,
                referenceId
        );
    }

    private DocumentWorkflow lock(UUID id) {
        try {
            return workflows.lockById(id).orElseThrow(() -> ApiException.notFound("Document workflow not found."));
        } catch (ObjectOptimisticLockingFailureException e) {
            throw conflict("The workflow changed concurrently. Reload and retry.");
        }
    }

    private DocumentWorkflow find(UUID id) {
        return workflows.findById(id).orElseThrow(() -> ApiException.notFound("Document workflow not found."));
    }

    private void requireReadable(DocumentWorkflow w, String actor, Set<String> authorities) {
        if (w.getOwnerUserId().equals(actor) && authorities.contains("DOCUMENT_VIEW")) return;
        if (authorities.contains("DOCUMENT_REVIEW_QUEUE_VIEW")
                && (w.getStatus() == DocumentWorkflowStatus.PENDING_STAFF_REVIEW
                || w.getStatus() == DocumentWorkflowStatus.STAFF_REVIEWING)
                && (w.getReviewerUserId() == null || w.getReviewerUserId().equals(actor))) return;
        if (authorities.contains("DOCUMENT_REVIEW") && actor.equals(w.getReviewerUserId())) return;
        if (authorities.contains("DOCUMENT_APPROVAL_QUEUE_VIEW")
                && (w.getStatus() == DocumentWorkflowStatus.PENDING_MANAGER_APPROVAL
                || w.getStatus() == DocumentWorkflowStatus.APPROVED
                || w.getStatus() == DocumentWorkflowStatus.REJECTED)) return;
        throw ApiException.notFound("Document workflow not found.");
    }

    private void requireOwner(DocumentWorkflow w, String actor) {
        if (!w.getOwnerUserId().equals(actor)) throw ApiException.notFound("Document workflow not found.");
    }

    private void requireDocumentOwner(JsonNode document, String ownerId) {
        if (!ownerId.equals(document.path("owner_user_id").asText(null))) {
            throw ApiException.notFound("Owned document not found.");
        }
    }

    private int documentVersionForSubmit(DocumentWorkflow workflow, JsonNode document) {
        int pending = document.path("pending_version").asInt(0);
        if (workflow.getStatus() == DocumentWorkflowStatus.CHANGES_REQUESTED) {
            Integer prior = workflow.getSubmittedDocumentVersion();
            if (pending <= 0 || prior == null || pending <= prior) {
                throw conflict("Update the document version before resubmitting.");
            }
            return pending;
        }
        if (pending > 0) return pending;
        int current = document.path("current_version").asInt(0);
        if (current < 1) throw conflict("The document has no readable version.");
        return current;
    }

    private int visibleDocumentVersion(DocumentWorkflow workflow, JsonNode document) {
        if (workflow.getStatus() == DocumentWorkflowStatus.DRAFT
                || workflow.getStatus() == DocumentWorkflowStatus.CHANGES_REQUESTED) {
            int pending = document.path("pending_version").asInt(0);
            return pending > 0 ? pending : document.path("current_version").asInt(1);
        }
        return workflow.getSubmittedDocumentVersion() == null ? 1 : workflow.getSubmittedDocumentVersion();
    }

    private void require(Set<String> authorities, String permission) {
        if (!authorities.contains(permission)) throw ApiException.forbidden("Missing permission: " + permission);
    }

    private void requireAnyRole(Set<String> authorities, String role) {
        if (!authorities.contains("ROLE_" + role) && !authorities.contains("ROLE_ADMINISTRATOR")
                && !authorities.contains("ROLE_ADMIN")) {
            throw ApiException.forbidden("The authenticated primary role cannot perform this workflow action.");
        }
    }

    private String requireRole(Set<String> authorities, String role) {
        if (!authorities.contains("ROLE_" + role)) {
            throw ApiException.forbidden("The authenticated primary role cannot perform this workflow action.");
        }
        return role;
    }

    private void requireAdministrator(Set<String> authorities) {
        if (!authorities.contains("ROLE_ADMINISTRATOR") && !authorities.contains("ROLE_ADMIN")) {
            throw ApiException.forbidden("Only an administrator can reassign a review.");
        }
    }

    private void record(DocumentWorkflow w, String actor, String action,
            DocumentWorkflowStatus previous, DocumentWorkflowStatus next, String comment) {
        record(w, actor, action, previous, next, comment, null, null);
    }

    private void record(DocumentWorkflow w, String actor, String action,
            DocumentWorkflowStatus previous, DocumentWorkflowStatus next, String comment,
            String previousReviewer, String newReviewer) {
        record(w, actor, action, previous, next, comment, previousReviewer, newReviewer, null);
    }

    private void record(DocumentWorkflow w, String actor, String action,
            DocumentWorkflowStatus previous, DocumentWorkflowStatus next, String comment,
            String previousReviewer, String newReviewer, String actorRole) {
        DocumentWorkflowAudit entry = new DocumentWorkflowAudit(w.getId(), actor, action,
                previous == null ? null : previous.name(), next.name(), normalizeComment(comment),
                previousReviewer, newReviewer, actorRole);
        entry.setDocumentVersion(w.getSubmittedDocumentVersion());
        audit.save(entry);
    }

    private static String normalizeComment(String comment) {
        return comment == null || comment.isBlank() ? null : comment.trim();
    }

    private static PageRequest page(int number, int size) {
        if (number < 0 || size < 1 || size > 100) throw ApiException.badRequest("page must be non-negative; size must be 1 to 100.");
        return PageRequest.of(number, size, Sort.by(Sort.Direction.ASC, "createdAt"));
    }

    private static <T> PageResponse<T> page(Page<T> p) {
        return new PageResponse<>(p.getContent(), p.getNumber(), p.getSize(), p.getTotalElements(),
                p.getTotalPages(), p.isFirst(), p.isLast());
    }

    private static WorkflowResponse toResponse(DocumentWorkflow w) {
        return new WorkflowResponse(w.getId(), w.getDocumentId(), w.getDocumentTitle(), w.getOwnerUserId(),
                w.getStatus(), w.getSubmittedDocumentVersion(), w.getReviewerUserId(), w.getStaffReviewResult(),
                w.getStaffComment(), w.getManagerUserId(), w.getManagerDecision(), w.getManagerComment(),
                w.getCreatedAt(), w.getUpdatedAt(), w.getSubmittedAt(), w.getReviewedAt(), w.getDecidedAt(),
                w.getOptimisticVersion());
    }

    private static ApiException conflict(String message) {
        return new ApiException(org.springframework.http.HttpStatus.CONFLICT, "WORKFLOW_CONFLICT", message);
    }
}