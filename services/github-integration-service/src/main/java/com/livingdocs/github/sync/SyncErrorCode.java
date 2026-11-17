package com.livingdocs.github.sync;

import org.springframework.http.HttpStatus;

/**
 * Các lỗi có thể xảy ra khi đồng bộ repository, kèm mã HTTP gợi ý cho API (phần của Minh).
 */
public enum SyncErrorCode {

    /** Tham số đồng bộ không hợp lệ (maxFiles âm, ngôn ngữ trống...). */
    INVALID_REQUEST(HttpStatus.BAD_REQUEST),
    /** Tên repository sai định dạng owner/repo. */
    INVALID_REPOSITORY(HttpStatus.BAD_REQUEST),
    /** Token GitHub hết hạn hoặc bị thu hồi: người dùng phải kết nối lại GitHub. */
    TOKEN_INVALID(HttpStatus.UNAUTHORIZED),
    /** GitHub App không có quyền đọc repo này, hoặc repo bị GitHub vô hiệu hoá. */
    ACCESS_DENIED(HttpStatus.FORBIDDEN),
    /** Repo không tồn tại, đã bị xoá, hoặc GitHub App chưa được cài cho repo này. */
    REPOSITORY_NOT_FOUND(HttpStatus.NOT_FOUND),
    /** Nhánh được yêu cầu không tồn tại. */
    BRANCH_NOT_FOUND(HttpStatus.NOT_FOUND),
    /** Repo chưa có commit nào. */
    EMPTY_REPOSITORY(HttpStatus.CONFLICT),
    /** Vượt giới hạn số lần gọi GitHub API: thử lại sau (xem retryAt). */
    RATE_LIMITED(HttpStatus.TOO_MANY_REQUESTS),
    /** Mất mạng, timeout hoặc GitHub lỗi 5xx: thử lại sau. */
    GITHUB_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE),
    /** GitHub trả về dữ liệu không như mong đợi. */
    UNEXPECTED_GITHUB_RESPONSE(HttpStatus.BAD_GATEWAY);

    private final HttpStatus httpStatus;

    SyncErrorCode(HttpStatus httpStatus) {
        this.httpStatus = httpStatus;
    }

    public HttpStatus httpStatus() {
        return httpStatus;
    }

    /** Có nên cho người dùng bấm "Thử lại" không. */
    public boolean retryable() {
        return this == RATE_LIMITED || this == GITHUB_UNAVAILABLE;
    }
}
