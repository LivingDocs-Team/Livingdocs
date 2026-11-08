package com.livingdocs.github.controller;

import java.util.Arrays;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

import org.springframework.http.HttpStatus;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import com.livingdocs.github.dto.WorkflowDtos.AuditResponse;
import com.livingdocs.github.dto.WorkflowDtos.ContentResponse;
import com.livingdocs.github.dto.WorkflowDtos.CreateWorkflowRequest;
import com.livingdocs.github.dto.WorkflowDtos.EditDocumentRequest;
import com.livingdocs.github.dto.WorkflowDtos.ManagerDecisionRequest;
import com.livingdocs.github.dto.WorkflowDtos.PageResponse;
import com.livingdocs.github.dto.WorkflowDtos.ReassignRequest;
import com.livingdocs.github.dto.WorkflowDtos.SaveGeneratedDocumentRequest;
import com.livingdocs.github.dto.WorkflowDtos.RollbackRequest;
import com.livingdocs.github.dto.WorkflowDtos.StaffReviewRequest;
import com.livingdocs.github.dto.WorkflowDtos.WorkflowResponse;
import com.livingdocs.github.entity.ManagerDecision;
import com.livingdocs.github.service.DocumentWorkflowService;
import com.livingdocs.github.service.DocumentationGenerationService;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

@RestController
@Validated
@RequestMapping("/api")
public class DocumentWorkflowController {
    static final String USER_HEADER = "X-User-Id";
    static final String AUTHORITIES_HEADER = "X-User-Authorities";

    private final DocumentWorkflowService workflowService;
    private final DocumentationGenerationService documentService;

    public DocumentWorkflowController(DocumentWorkflowService workflowService,
            DocumentationGenerationService documentService) {
        this.workflowService = workflowService;
        this.documentService = documentService;
    }

    @PostMapping("/documentation/jobs/{jobId}/document")
    @ResponseStatus(HttpStatus.CREATED)
    public com.fasterxml.jackson.databind.JsonNode saveGeneratedDocument(
            @RequestHeader(USER_HEADER) String userId,
            @RequestHeader(AUTHORITIES_HEADER) String authorities,
            @PathVariable String jobId,
            @Valid @RequestBody(required = false) SaveGeneratedDocumentRequest request) {
        return documentService.saveOwnedDocument(userId, parse(authorities), jobId,
                request == null ? null : request.title());
    }

    @PostMapping("/document-workflows")
    @ResponseStatus(HttpStatus.CREATED)
    public WorkflowResponse create(@RequestHeader(USER_HEADER) String userId,
            @RequestHeader(AUTHORITIES_HEADER) String authorities,
            @Valid @RequestBody CreateWorkflowRequest request) {
        return workflowService.create(userId, parse(authorities), request.documentId());
    }

    @GetMapping("/document-workflows/mine")
    public PageResponse<WorkflowResponse> mine(@RequestHeader(USER_HEADER) String userId,
            @RequestHeader(AUTHORITIES_HEADER) String authorities,
            @RequestParam(defaultValue = "0") int page, @RequestParam(defaultValue = "20") int size) {
        return workflowService.mine(userId, parse(authorities), page, size);
    }

    @GetMapping("/document-workflows/staff/queue")
    public PageResponse<WorkflowResponse> staffQueue(@RequestHeader(USER_HEADER) String userId,
            @RequestHeader(AUTHORITIES_HEADER) String authorities,
            @RequestParam(defaultValue = "0") int page, @RequestParam(defaultValue = "20") int size) {
        return workflowService.staffQueue(userId, parse(authorities), page, size);
    }

    @GetMapping("/document-workflows/manager/queue")
    public PageResponse<WorkflowResponse> managerQueue(@RequestHeader(USER_HEADER) String userId,
            @RequestHeader(AUTHORITIES_HEADER) String authorities,
            @RequestParam(defaultValue = "0") int page, @RequestParam(defaultValue = "20") int size) {
        return workflowService.managerQueue(parse(authorities), page, size);
    }

    @GetMapping("/document-workflows/{id}")
    public WorkflowResponse get(@RequestHeader(USER_HEADER) String userId,
            @RequestHeader(AUTHORITIES_HEADER) String authorities, @PathVariable UUID id) {
        return workflowService.get(userId, parse(authorities), id);
    }

    @GetMapping("/document-workflows/{id}/document")
    public ContentResponse content(@RequestHeader(USER_HEADER) String userId,
            @RequestHeader(AUTHORITIES_HEADER) String authorities, @PathVariable UUID id) {
        return workflowService.content(userId, parse(authorities), id);
    }
    @GetMapping("/document-workflows/{id}/evidence")
    public com.fasterxml.jackson.databind.JsonNode evidence(
        @RequestHeader(USER_HEADER) String userId,
        @RequestHeader(AUTHORITIES_HEADER) String authorities,
        @PathVariable UUID id) {
    return workflowService.evidence(userId, parse(authorities), id);
    }

    @GetMapping("/document-workflows/{id}/history")
    public java.util.List<AuditResponse> history(@RequestHeader(USER_HEADER) String userId,
            @RequestHeader(AUTHORITIES_HEADER) String authorities, @PathVariable UUID id) {
        return workflowService.history(userId, parse(authorities), id);
    }

    @PostMapping("/document-workflows/{id}/submit")
    public WorkflowResponse submit(@RequestHeader(USER_HEADER) String userId,
            @RequestHeader(AUTHORITIES_HEADER) String authorities, @PathVariable UUID id) {
        return workflowService.submit(userId, parse(authorities), id);
    }

    @PostMapping("/document-workflows/{id}/claim")
    public WorkflowResponse claim(@RequestHeader(USER_HEADER) String userId,
            @RequestHeader(AUTHORITIES_HEADER) String authorities, @PathVariable UUID id) {
        return workflowService.claim(userId, parse(authorities), id);
    }

    @PostMapping("/document-workflows/{id}/release")
    public WorkflowResponse release(@RequestHeader(USER_HEADER) String userId,
            @RequestHeader(AUTHORITIES_HEADER) String authorities, @PathVariable UUID id) {
        return workflowService.release(userId, parse(authorities), id);
    }

    @PostMapping("/document-workflows/{id}/reassign")
    public WorkflowResponse reassign(@RequestHeader(USER_HEADER) String userId,
            @RequestHeader(AUTHORITIES_HEADER) String authorities,
            @RequestHeader("X-Verified-Staff-User-Id") String verifiedStaffUserId,
            @PathVariable UUID id, @Valid @RequestBody ReassignRequest request) {
        return workflowService.reassign(userId, parse(authorities), id, verifiedStaffUserId, request);
    }

    @PostMapping("/document-workflows/{id}/staff-review")
    public WorkflowResponse review(@RequestHeader(USER_HEADER) String userId,
            @RequestHeader(AUTHORITIES_HEADER) String authorities, @PathVariable UUID id,
            @Valid @RequestBody StaffReviewRequest request) {
        return workflowService.staffReview(userId, parse(authorities), id, request);
    }

    @PutMapping("/document-workflows/{id}/document")
    public WorkflowResponse editAfterChanges(@RequestHeader(USER_HEADER) String userId,
            @RequestHeader(AUTHORITIES_HEADER) String authorities, @PathVariable UUID id,
            @Valid @RequestBody EditDocumentRequest request) {
        return workflowService.editAfterChanges(userId, parse(authorities), id, request);
    }
    @PostMapping("/document-workflows/{id}/approve")
    public WorkflowResponse approve(@RequestHeader(USER_HEADER) String userId,
            @RequestHeader(AUTHORITIES_HEADER) String authorities, @PathVariable UUID id,
            @Valid @RequestBody(required = false) ManagerDecisionRequest request) {
        return workflowService.decide(userId, parse(authorities), id, ManagerDecision.APPROVED,
                request == null ? null : request.comment());
    }

    @PostMapping("/document-workflows/{id}/reject")
    public WorkflowResponse reject(@RequestHeader(USER_HEADER) String userId,
            @RequestHeader(AUTHORITIES_HEADER) String authorities, @PathVariable UUID id,
            @Valid @RequestBody(required = false) ManagerDecisionRequest request) {
        return workflowService.decide(userId, parse(authorities), id, ManagerDecision.REJECTED,
                request == null ? null : request.comment());
    }
    @PostMapping("/document-workflows/{id}/rollback")
    public WorkflowResponse rollback(
        @RequestHeader(USER_HEADER) String userId,
        @RequestHeader(AUTHORITIES_HEADER) String authorities,
        @PathVariable UUID id,
        @Valid @RequestBody RollbackRequest request) {

    return workflowService.rollback(
            userId,
            parse(authorities),
            id,
            request.sourceVersion(),
            request.reason()
    );
}
    private Set<String> parse(String value) {
        if (value == null || value.isBlank()) return Set.of();
        return Arrays.stream(value.split(",")).map(String::trim).filter(s -> !s.isEmpty())
                .collect(Collectors.toUnmodifiableSet());
    }
}
