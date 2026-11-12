package com.livingdocs.github.dto;

import com.livingdocs.github.entity.SourceChange;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * LD-116: một source change cho bước cập nhật tài liệu (LD-128).
 *
 * @param trigger           COMMIT hoặc PULL_REQUEST
 * @param status            PENDING (đã phát hiện, chờ cập nhật tài liệu) hoặc FAILED (xem errorCode, gọi retry)
 * @param documentsStatus   LD-122: PENDING (đang tìm tài liệu bị ảnh hưởng), FOUND (xem affectedDocuments)
 *                          hoặc FAILED (xem documentsErrorCode, gọi retry); null khi status là FAILED
 * @param affectedDocuments phần tài liệu đã lưu có thể đã cũ, DIRECT trước DEPENDENT
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
        List<FileResponse> files,
        String documentsStatus,
        String documentsErrorCode,
        String documentsErrorMessage,
        List<DocumentResponse> affectedDocuments) {

    /** change: ADDED, MODIFIED, REMOVED, RENAMED. skippedReason khác null: không tìm code entity được cho file này. */
    public record FileResponse(String path, String previousPath, String change, String language,
                               Integer additions, Integer deletions, String skippedReason,
                               List<EntityResponse> entities) {
    }

    /** startLine, endLine: dòng trong file sau thay đổi (REMOVED: dòng trong file trước thay đổi). */
    public record EntityResponse(String kind, String name, String change, int startLine, int endLine) {
    }

    /**
     * LD-124 / LD-125: một phần (theo file) của tài liệu đã lưu ở ai-service.
     *
     * @param section       phần tài liệu bị ảnh hưởng (đường dẫn file mà phần đó mô tả)
     * @param documentsFile file mã nguồn mà phần này được sinh ra từ đó
     * @param dependency    DIRECT: phần của chính file thay đổi; DEPENDENT: phần khác nhắc tới code đã thay đổi
     * @param reasons       vd. "documents changed file shop/cart.py", "mentions `Invoice.total`"
     * @param evidence      LD-126: các chỗ trong phần tài liệu nhắc tới code đã thay đổi (tối đa 20, theo dòng)
     */
    public record DocumentResponse(String documentId, String title, Integer version, String section,
                                   String documentsFile, String dependency, List<String> reasons,
                                   List<EvidenceResponse> evidence) {
    }

    /** target: entity, endpoint hoặc đường dẫn đã thay đổi; line: dòng trong phần tài liệu; excerpt: đoạn trích dòng đó. */
    public record EvidenceResponse(String target, String kind, int line, String excerpt) {
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
        List<DocumentResponse> documents = c.getAffectedDocuments().stream()
                .map(d -> new DocumentResponse(d.getDocumentId(), d.getTitle(), d.getVersion(), d.getSectionPath(),
                        d.getDocumentsFile(), d.getDependency().name(), d.getReasons(),
                        d.getEvidence().stream()
                                .map(e -> new EvidenceResponse(e.getTarget(), e.getKind(), e.getLine(), e.getExcerpt()))
                                .toList()))
                .toList();
        return new SourceChangeResponse(c.getId(), c.getTriggerType().name(), c.getCommitSha(),
                c.getPullRequestNumber(), c.getStatus().name(), c.getErrorCode(), c.getErrorMessage(),
                c.getCreatedAt(), c.getUpdatedAt(), files,
                c.getDocumentsStatus() == null ? null : c.getDocumentsStatus().name(),
                c.getDocumentsErrorCode(), c.getDocumentsErrorMessage(), documents);
    }
}
