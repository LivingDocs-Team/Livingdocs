package com.livingdocs.github.sync;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonPropertyOrder;

import java.util.List;

/**
 * Dữ liệu gửi sang service phân tích code: body của {@code POST /api/v1/analyze-repo} (contract LD-395).
 * Nội dung file được gửi kèm, vì service phân tích không có sẵn code của repo trên máy.
 * Ví dụ: {@code docs/samples/analysis-input.sample.json}.
 *
 * @param repoName tên đầy đủ của repo, ví dụ LivingDocs-Team/Livingdocs (analyzer đọc trường "repo_name")
 * @param scope    luôn là "repository"
 * @param target   tên repo, giống repoName; giữ lại cho các bên đang đọc trường "target"
 * @param files    các file đã tải được nội dung
 */
@JsonPropertyOrder({"repo_name", "scope", "target", "files"})
public record AnalysisInput(
        @JsonProperty("repo_name") String repoName,
        String scope,
        String target,
        List<FileInput> files) {

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
        String fullName = snapshot.repository().fullName();
        return new AnalysisInput(fullName, "repository", fullName, files);
    }
}
