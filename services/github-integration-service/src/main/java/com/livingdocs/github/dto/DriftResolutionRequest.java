package com.livingdocs.github.dto;

/**
 * Xử lý một phát hiện lệch tài liệu (LD-346).
 *
 * @param status open | acknowledged | resolved | dismissed
 * @param note   ghi chú; bắt buộc khi dismissed (lý do không phải lệch tài liệu)
 */
public record DriftResolutionRequest(String status, String note) {
}
