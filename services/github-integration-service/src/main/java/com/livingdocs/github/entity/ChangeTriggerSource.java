package com.livingdocs.github.entity;

public enum ChangeTriggerSource {
    AI_GENERATION,      // Sinh tài liệu tự động từ kết quả phân tích code
    MANUAL_EDIT,        // Người dùng tạo hoặc chỉnh sửa trực tiếp trên trình soạn thảo
    DRIFT_SUGGESTION,   // Áp dụng gợi ý cập nhật từ phát hiện Documentation Drift
    PR_WEBHOOK,         // Kích hoạt từ sự kiện Push / Pull Request trên GitHub
    REVIEW_WORKFLOW,    // Thao tác tạo workflow, gửi duyệt, nhận duyệt, phê duyệt, từ chối
    ROLLBACK            // Khôi phục về phiên bản tài liệu trước đó
}