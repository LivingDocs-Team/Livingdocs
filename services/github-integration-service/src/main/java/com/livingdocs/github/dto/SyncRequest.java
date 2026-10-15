package com.livingdocs.github.dto;

import com.livingdocs.github.sync.SyncOptions;

/**
 * Body của POST /api/repositories/{id}/sync. Mọi field đều không bắt buộc, bỏ trống thì dùng mặc định.
 *
 * @param branch         nhánh cần đồng bộ; bỏ trống = nhánh mặc định của repo
 * @param includeContent có tải nội dung file không (mặc định true, cần cho bước phân tích code)
 * @param maxFiles       số file nguồn tối đa, 1..1000 (mặc định 200)
 */
public record SyncRequest(String branch, Boolean includeContent, Integer maxFiles) {

    /** Giá trị sai (ví dụ maxFiles = 0) sẽ ném INVALID_REQUEST, GlobalExceptionHandler trả 400. */
    public SyncOptions toOptions() {
        SyncOptions options = SyncOptions.defaults();
        if (branch != null) {
            options = options.withBranch(branch.trim());
        }
        if (includeContent != null) {
            options = options.withIncludeContent(includeContent);
        }
        if (maxFiles != null) {
            options = options.withMaxFiles(maxFiles);
        }
        return options;
    }
}
