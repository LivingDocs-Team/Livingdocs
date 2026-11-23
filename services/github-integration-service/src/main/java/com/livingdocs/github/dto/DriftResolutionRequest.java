package com.livingdocs.github.dto;

/**
 * Xử lý một phát hiện lệch tài liệu (LD-346).
 *
 * @param status open | acknowledged | resolved | dismissed
 * @param note   ghi chú; bắt buộc khi dismissed (lý do không phải lệch tài liệu)
 * @param acceptedUpdate LD-161: nội dung tài liệu được chấp nhận khi resolved (gợi ý AI nguyên văn
 *                       hoặc đã sửa); chỉ dùng với status resolved
 * @param decision lựa chọn trong luồng tạo bản nháp
 * @param proposed nội dung chỉnh sửa cho bản nháp
 */
public record DriftResolutionRequest(
        String status, String note, String acceptedUpdate, String decision, String proposed, Integer retryOf) {

    public DriftResolutionRequest(String status, String note) {
        this(status, note, null, null, null, null);
    }

    public DriftResolutionRequest(String status, String note, String acceptedUpdate) {
        this(status, note, acceptedUpdate, null, null, null);
    }

    public DriftResolutionRequest(String status, String note, String decision, String proposed) {
        this(status, note, null, decision, proposed, null);
    }
}
