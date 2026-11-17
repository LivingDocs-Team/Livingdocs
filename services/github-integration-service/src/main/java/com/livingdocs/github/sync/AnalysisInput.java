package com.livingdocs.github.sync;

import java.util.List;

/**
 * Dữ liệu gửi sang service phân tích code (LD-328): body của {@code POST /api/v1/analyze-repo}.
 * Nội dung file được gửi kèm, vì service phân tích không có sẵn code của repo trên máy.
 * Ví dụ: {@code docs/samples/analysis-input.sample.json}.
 *
 * @param scope  luôn là "repository"
 * @param target tên đầy đủ của repo, ví dụ LivingDocs-Team/Livingdocs
 * @param files  các file đã tải được nội dung
 */
public record AnalysisInput(String scope, String target, List<FileInput> files) {

    public AnalysisInput {
        files = files == null ? List.of() : List.copyOf(files);
    }

    public record FileInput(String path, String language, String content) {
    }

    /** Chuyển kết quả đồng bộ thành dữ liệu cho service phân tích. File không có nội dung bị bỏ qua. */
    public static AnalysisInput from(RepositorySnapshot snapshot) {
        List<FileInput> files = snapshot.analyzableFiles().stream()
                .map(f -> new FileInput(f.path(), f.language(), f.content()))
                .toList();
        return new AnalysisInput("repository", snapshot.repository().fullName(), files);
    }
}
