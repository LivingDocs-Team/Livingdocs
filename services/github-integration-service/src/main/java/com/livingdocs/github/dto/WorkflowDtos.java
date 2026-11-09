package com.livingdocs.github.dto;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.livingdocs.github.entity.DocumentWorkflowStatus;
import com.livingdocs.github.entity.ManagerDecision;
import com.livingdocs.github.entity.StaffReviewResult;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public final class WorkflowDtos {
    private WorkflowDtos() { }

    public record SaveGeneratedDocumentRequest(@Size(max = 200) String title) { }
    public record CreateWorkflowRequest(@NotBlank @Size(max = 64) String documentId) { }
    public record StaffReviewRequest(@NotNull StaffReviewResult result,
                                     @Size(max = 2000) String comment) { }
    public record ManagerDecisionRequest(@Size(max = 2000) String comment) { }
    public record ReassignRequest(@NotNull @Positive Long targetStaffUserId,
                                 @NotBlank @Size(max = 1000) String reason) { }
    public record EditDocumentRequest(@NotBlank @Size(max = 2_000_000) String content,
                                      @Size(max = 1000) String note) { }
    public record RollbackRequest(
        @NotNull @Positive Integer sourceVersion,
        @NotBlank @Size(max = 1000) String reason
) { }
    public record WorkflowResponse(UUID id, String documentId, String documentTitle, String ownerUserId,
            DocumentWorkflowStatus status, Integer submittedDocumentVersion, String reviewerUserId,
            StaffReviewResult staffReviewResult, String staffComment, String managerUserId,
            ManagerDecision managerDecision, String managerComment, Instant createdAt, Instant updatedAt,
            Instant submittedAt, Instant reviewedAt, Instant decidedAt, long optimisticVersion) { }

    public record ContentResponse(String documentId, int version, String content) { }
    public record AuditResponse(UUID id, String actorUserId, String actorRole, String action, String previousStatus,
            String newStatus, String previousReviewerUserId, String newReviewerUserId,
            String comment, Instant createdAt) { }
    public record PageResponse<T>(List<T> content, int page, int size, long totalElements,
            int totalPages, boolean first, boolean last) { }
}
