package com.livingdocs.github.sync;

import java.time.Instant;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Kết quả đồng bộ một repository tại một commit cụ thể.
 * Đây là "hợp đồng dữ liệu" giữa phần lấy dữ liệu GitHub (Đăng) và API đồng bộ (Minh).
 *
 * @param repository    thông tin repo
 * @param branch        nhánh đã đồng bộ
 * @param headCommit    commit mới nhất của nhánh, mọi file đều lấy theo commit này
 * @param languages     số byte code theo ngôn ngữ (theo GitHub), ví dụ {"Java": 12000}
 * @param files         các file nguồn được chọn, sắp xếp theo path
 * @param recentCommits các commit gần nhất (mới nhất trước)
 * @param stats         thống kê để kiểm tra nhanh
 * @param warnings      cảnh báo (không phải lỗi)
 * @param fetchedAt     thời điểm lấy dữ liệu
 */
public record RepositorySnapshot(
        RepositoryInfo repository,
        String branch,
        CommitInfo headCommit,
        Map<String, Long> languages,
        List<SourceFile> files,
        List<CommitInfo> recentCommits,
        SyncStats stats,
        List<SyncWarning> warnings,
        Instant fetchedAt) {

    public RepositorySnapshot {
        // Giữ nguyên thứ tự GitHub trả về (ngôn ngữ nhiều code nhất đứng đầu)
        languages = languages == null ? Map.of() : Collections.unmodifiableMap(new LinkedHashMap<>(languages));
        files = files == null ? List.of() : List.copyOf(files);
        recentCommits = recentCommits == null ? List.of() : List.copyOf(recentCommits);
        warnings = warnings == null ? List.of() : List.copyOf(warnings);
    }

    /** Các file đã có nội dung, sẵn sàng gửi sang service phân tích code (xem {@link AnalysisInput}). */
    public List<SourceFile> analyzableFiles() {
        return files.stream().filter(SourceFile::hasContent).toList();
    }

    public record RepositoryInfo(
            Long githubRepoId,
            String fullName,
            String owner,
            String name,
            String description,
            boolean privateRepo,
            boolean archived,
            String defaultBranch,
            String htmlUrl,
            String primaryLanguage,
            Long sizeKb,
            Instant pushedAt) {
    }

    /** Thông tin commit. Không lưu email tác giả để tránh lộ thông tin cá nhân. */
    public record CommitInfo(
            String sha,
            String message,
            String authorName,
            String authorLogin,
            Instant committedAt,
            String htmlUrl) {
    }

    /**
     * Một file nguồn.
     *
     * @param path       đường dẫn trong repo, ví dụ src/main/java/App.java
     * @param sha        SHA của file (blob) tại commit đồng bộ
     * @param size       kích thước (byte)
     * @param language   "java", "python"... (viết thường, đúng giá trị service phân tích code cần)
     * @param content    nội dung UTF-8; null nếu không tải (xem skipReason)
     * @param skipReason lý do không có nội dung; null nếu đã tải được
     */
    public record SourceFile(
            String path,
            String sha,
            long size,
            String language,
            String content,
            SkipReason skipReason) {

        public boolean hasContent() {
            return content != null;
        }
    }

    public enum SkipReason {
        /** Không yêu cầu tải nội dung (includeContent = false). */
        NOT_REQUESTED,
        /** File lớn hơn maxFileSizeBytes. */
        TOO_LARGE,
        /** File nhị phân, không phải văn bản. */
        BINARY,
        /** GitHub không trả được nội dung file này. */
        UNAVAILABLE
    }

    /**
     * @param totalFilesInRepo  tổng số file trong repo (theo cây thư mục GitHub trả về)
     * @param filesSelected     số file nguồn được chọn (đúng ngôn ngữ, không nằm trong thư mục bị bỏ qua)
     * @param filesWithContent  số file đã tải được nội dung
     * @param filesIgnored      số file bị bỏ qua (không phải code, thư mục build/node_modules, vượt giới hạn...)
     * @param treeTruncated     GitHub chỉ trả một phần cây thư mục (repo quá lớn)
     * @param fileLimitReached  đã chạm maxFiles, còn file nguồn chưa được chọn
     */
    public record SyncStats(
            int totalFilesInRepo,
            int filesSelected,
            int filesWithContent,
            int filesIgnored,
            boolean treeTruncated,
            boolean fileLimitReached) {
    }
}
