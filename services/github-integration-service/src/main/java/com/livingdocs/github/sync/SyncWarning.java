package com.livingdocs.github.sync;

/**
 * Cảnh báo không làm hỏng việc đồng bộ nhưng người dùng / module sau nên biết.
 * Ví dụ: TREE_TRUNCATED, FILE_LIMIT_REACHED, ARCHIVED_REPOSITORY, REPOSITORY_RENAMED.
 */
public record SyncWarning(String code, String message) {
}
