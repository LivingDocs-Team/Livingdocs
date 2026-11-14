package com.livingdocs.github.dto;

import com.livingdocs.github.entity.SourceChange;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * LD-116: một source change cho bước cập nhật tài liệu (LD-128).
 *
 * @param trigger COMMIT hoặc PULL_REQUEST
 * @param status  PENDING (đã phát hiện, chờ cập nhật tài liệu) hoặc FAILED (xem errorCode, gọi retry)
 */
public record SourceChangeResponse(
        UUID id,
        String trigger,
        String commitSha,
        Integer pullRequestNumber,
        String status,
        String errorCode,
        String errorMessage,
        Instant createdAt,
        Instant updatedAt,
        List<FileResponse> files) {

    /** change: ADDED, MODIFIED, REMOVED, RENAMED. skippedReason khác null: không tìm code entity được cho file này. */
    public record FileResponse(String path, String previousPath, String change, String language,
                               Integer additions, Integer deletions, String skippedReason,
                               List<EntityResponse> entities) {
    }

    /** startLine, endLine: dòng trong file sau thay đổi (REMOVED: dòng trong file trước thay đổi). */
    public record EntityResponse(String kind, String name, String change, int startLine, int endLine) {
    }

    public static SourceChangeResponse from(SourceChange c) {
        List<FileResponse> files = c.getFiles().stream()
                .map(f -> new FileResponse(f.getPath(), f.getPreviousPath(), f.getChangeType(), f.getLanguage(),
                        f.getAdditions(), f.getDeletions(), f.getSkippedReason(),
                        f.getEntities().stream()
                                .map(e -> new EntityResponse(e.getKind(), e.getName(), e.getChangeType(),
                                        e.getStartLine(), e.getEndLine()))
                                .toList()))
                .toList();
        return new SourceChangeResponse(c.getId(), c.getTriggerType().name(), c.getCommitSha(),
                c.getPullRequestNumber(), c.getStatus().name(), c.getErrorCode(), c.getErrorMessage(),
                c.getCreatedAt(), c.getUpdatedAt(), files);
    }
}



