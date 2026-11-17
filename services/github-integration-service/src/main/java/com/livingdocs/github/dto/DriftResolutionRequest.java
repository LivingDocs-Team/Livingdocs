package com.livingdocs.github.dto;

/**
 * Xử lý một phát hiện lệch tài liệu (LD-346).
 *
 * @param status open | acknowledged | resolved | dismissed
 * @param note   ghi chú; bắt buộc khi dismissed (lý do không phải lệch tài liệu)
 * @param acceptedUpdate LD-161: nội dung tài liệu được chấp nhận khi resolved (gợi ý AI nguyên văn
 *                       hoặc đã sửa); chỉ dùng với status resolved
 */
public record DriftResolutionRequest(String status, String note, String acceptedUpdate) {

    public DriftResolutionRequest(String status, String note) {
        this(status, note, null);
    }
}
