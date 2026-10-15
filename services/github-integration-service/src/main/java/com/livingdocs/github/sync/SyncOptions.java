package com.livingdocs.github.sync;

import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;

/**
 * Tuỳ chọn khi đồng bộ.
 *
 * @param branch             nhánh cần đồng bộ; null = nhánh mặc định của repo
 * @param includeContent     có tải nội dung file hay không (cần cho bước phân tích code)
 * @param maxFiles           số file nguồn tối đa được chọn (bảo vệ giới hạn gọi API)
 * @param maxFileSizeBytes   file lớn hơn mức này sẽ bị bỏ qua nội dung
 * @param recentCommitLimit  số commit gần nhất cần lấy
 * @param languages          ngôn ngữ cần lấy file, mặc định là ngôn ngữ module phân tích hỗ trợ (java, python)
 */
public record SyncOptions(
        String branch,
        boolean includeContent,
        int maxFiles,
        long maxFileSizeBytes,
        int recentCommitLimit,
        Set<String> languages) {

    public static final int DEFAULT_MAX_FILES = 200;
    public static final int MAX_FILES_LIMIT = 1000;
    public static final long DEFAULT_MAX_FILE_SIZE_BYTES = 200_000;
    public static final int DEFAULT_RECENT_COMMITS = 20;
    /** Ngôn ngữ mà service phân tích code (POST /api/v1/analyze-repo) đang hỗ trợ. */
    public static final Set<String> ANALYZER_LANGUAGES = Set.of("java", "python");

    public SyncOptions {
        if (maxFiles < 1 || maxFiles > MAX_FILES_LIMIT) {
            throw new RepositorySyncException(SyncErrorCode.INVALID_REQUEST,
                    "maxFiles phải nằm trong khoảng 1.." + MAX_FILES_LIMIT);
        }
        if (maxFileSizeBytes < 1) {
            throw new RepositorySyncException(SyncErrorCode.INVALID_REQUEST, "maxFileSizeBytes phải lớn hơn 0");
        }
        if (recentCommitLimit < 0 || recentCommitLimit > 100) {
            throw new RepositorySyncException(SyncErrorCode.INVALID_REQUEST, "recentCommitLimit phải nằm trong khoảng 0..100");
        }
        if (branch != null && branch.isBlank()) {
            branch = null;
        }
        languages = normalize(languages);
    }

    public static SyncOptions defaults() {
        return new SyncOptions(null, true, DEFAULT_MAX_FILES, DEFAULT_MAX_FILE_SIZE_BYTES,
                DEFAULT_RECENT_COMMITS, ANALYZER_LANGUAGES);
    }

    public SyncOptions withBranch(String newBranch) {
        return new SyncOptions(newBranch, includeContent, maxFiles, maxFileSizeBytes, recentCommitLimit, languages);
    }

    public SyncOptions withIncludeContent(boolean newIncludeContent) {
        return new SyncOptions(branch, newIncludeContent, maxFiles, maxFileSizeBytes, recentCommitLimit, languages);
    }

    public SyncOptions withMaxFiles(int newMaxFiles) {
        return new SyncOptions(branch, includeContent, newMaxFiles, maxFileSizeBytes, recentCommitLimit, languages);
    }

    public SyncOptions withMaxFileSizeBytes(long newMaxFileSizeBytes) {
        return new SyncOptions(branch, includeContent, maxFiles, newMaxFileSizeBytes, recentCommitLimit, languages);
    }

    private static Set<String> normalize(Set<String> input) {
        if (input == null || input.isEmpty()) {
            return ANALYZER_LANGUAGES;
        }
        Set<String> result = new LinkedHashSet<>();
        for (String language : input) {
            if (language != null && !language.isBlank()) {
                result.add(language.trim().toLowerCase(Locale.ROOT));
            }
        }
        return result.isEmpty() ? ANALYZER_LANGUAGES : Set.copyOf(result);
    }
}
