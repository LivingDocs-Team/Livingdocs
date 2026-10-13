package com.livingdocs.github.dto;

import com.livingdocs.github.sync.RepositorySnapshot;
import com.livingdocs.github.sync.SyncWarning;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * Kết quả đồng bộ trả cho frontend: không kèm nội dung file cho nhẹ
 * (nội dung lấy ở GET /api/repositories/{id}/sync/latest/analysis-input).
 * Ví dụ: docs/samples/sync-api-response.sample.json.
 */
public record SyncResultResponse(
        RepositorySnapshot.RepositoryInfo repository,
        String branch,
        RepositorySnapshot.CommitInfo headCommit,
        Map<String, Long> languages,
        List<FileItem> files,
        RepositorySnapshot.SyncStats stats,
        List<SyncWarning> warnings,
        Instant syncedAt) {

    /**
     * @param analyzable có nội dung, sẽ được gửi sang service phân tích code
     * @param skipReason lý do không có nội dung (NOT_REQUESTED, TOO_LARGE, BINARY, UNAVAILABLE); null nếu có
     */
    public record FileItem(String path, String language, long size, boolean analyzable, String skipReason) {
    }

    public static SyncResultResponse from(RepositorySnapshot snapshot) {
        List<FileItem> files = snapshot.files().stream()
                .map(f -> new FileItem(f.path(), f.language(), f.size(), f.hasContent(),
                        f.skipReason() == null ? null : f.skipReason().name()))
                .toList();
        return new SyncResultResponse(snapshot.repository(), snapshot.branch(), snapshot.headCommit(),
                snapshot.languages(), files, snapshot.stats(), snapshot.warnings(), snapshot.fetchedAt());
    }
}
