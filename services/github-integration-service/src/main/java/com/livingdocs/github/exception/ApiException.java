package com.livingdocs.github.exception;

import org.springframework.http.HttpStatus;

/** Lỗi nghiệp vụ, được GlobalExceptionHandler chuyển thành JSON trả cho client. */
public class ApiException extends RuntimeException {

    private final HttpStatus status;
    private final String code;

    public ApiException(HttpStatus status, String code, String message) {
        super(message);
        this.status = status;
        this.code = code;
    }

    public HttpStatus getStatus() { return status; }

    public String getCode() { return code; }

    public static ApiException notFound(String message) {
        return new ApiException(HttpStatus.NOT_FOUND, "NOT_FOUND", message);
    }

    public static ApiException badRequest(String message) {
        return new ApiException(HttpStatus.BAD_REQUEST, "BAD_REQUEST", message);
    }

    public static ApiException forbidden(String message) {
        return new ApiException(HttpStatus.FORBIDDEN, "FORBIDDEN", message);
    }

    public static ApiException githubNotConnected() {
        return new ApiException(HttpStatus.CONFLICT, "GITHUB_NOT_CONNECTED",
                "Bạn chưa kết nối GitHub hoặc kết nối đã bị ngắt. Hãy kết nối lại.");
    }

    public static ApiException githubReauthRequired() {
        return new ApiException(HttpStatus.UNAUTHORIZED, "GITHUB_REAUTH_REQUIRED",
                "Token GitHub không còn hợp lệ. Hãy kết nối lại GitHub.");
    }
}
