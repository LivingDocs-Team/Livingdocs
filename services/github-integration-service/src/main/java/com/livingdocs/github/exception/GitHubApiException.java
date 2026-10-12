package com.livingdocs.github.exception;

import org.springframework.http.HttpHeaders;

import java.time.Instant;
import java.util.Locale;

/**
 * Lỗi khi gọi GitHub API.
 *
 * Giữ lại mã HTTP và các header rate limit để tầng trên (ví dụ đồng bộ repository)
 * phân biệt được: token hỏng (401), không có quyền (403), không tìm thấy (404),
 * repo rỗng (409), vượt giới hạn gọi API (403/429), GitHub lỗi (5xx) hay mất mạng (statusCode = 0).
 */
public class GitHubApiException extends RuntimeException {

    private final int statusCode;
    private final Long rateLimitRemaining;
    private final Instant rateLimitReset;
    private final Long retryAfterSeconds;
    private final String responseBody;

    /** Giữ lại để tương thích với code cũ: unauthorized = true tương đương HTTP 401. */
    public GitHubApiException(String message, boolean unauthorized) {
        this(message, unauthorized ? 401 : 0, null, null, null, null);
    }

    /** Lỗi mạng / timeout: không nhận được phản hồi nào từ GitHub. */
    public GitHubApiException(String message, Throwable cause) {
        super(message, cause);
        this.statusCode = 0;
        this.rateLimitRemaining = null;
        this.rateLimitReset = null;
        this.retryAfterSeconds = null;
        this.responseBody = null;
    }

    /** GitHub có trả về phản hồi lỗi (4xx, 5xx). */
    public GitHubApiException(String message, int statusCode, HttpHeaders headers, String responseBody) {
        this(message, statusCode,
                parseLong(headers, "x-ratelimit-remaining"),
                parseEpochSeconds(headers, "x-ratelimit-reset"),
                parseLong(headers, "retry-after"),
                responseBody);
    }

    private GitHubApiException(String message, int statusCode, Long rateLimitRemaining,
                               Instant rateLimitReset, Long retryAfterSeconds, String responseBody) {
        super(message);
        this.statusCode = statusCode;
        this.rateLimitRemaining = rateLimitRemaining;
        this.rateLimitReset = rateLimitReset;
        this.retryAfterSeconds = retryAfterSeconds;
        this.responseBody = responseBody;
    }

    /** Mã HTTP GitHub trả về; 0 nếu không nhận được phản hồi (lỗi mạng). */
    public int getStatusCode() { return statusCode; }

    public String getResponseBody() { return responseBody; }

    public boolean isUnauthorized() { return statusCode == 401; }

    public boolean isNotFound() { return statusCode == 404; }

    public boolean isConflict() { return statusCode == 409; }

    public boolean isServerError() { return statusCode >= 500; }

    public boolean isNetworkError() { return statusCode == 0 && getCause() != null; }

    /**
     * GitHub báo vượt giới hạn gọi API bằng HTTP 429, hoặc HTTP 403 kèm
     * x-ratelimit-remaining = 0 / Retry-After / thông báo "rate limit" trong nội dung.
     */
    public boolean isRateLimited() {
        if (statusCode == 429) {
            return true;
        }
        if (statusCode != 403) {
            return false;
        }
        if (rateLimitRemaining != null && rateLimitRemaining == 0) {
            return true;
        }
        if (retryAfterSeconds != null) {
            return true;
        }
        return responseBody != null && responseBody.toLowerCase(Locale.ROOT).contains("rate limit");
    }

    /** Thời điểm nên thử lại khi bị rate limit (null nếu GitHub không cho biết). */
    public Instant retryAt() {
        if (retryAfterSeconds != null) {
            return Instant.now().plusSeconds(retryAfterSeconds);
        }
        return rateLimitReset;
    }

    private static Long parseLong(HttpHeaders headers, String name) {
        if (headers == null) {
            return null;
        }
        String value = headers.getFirst(name);
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return Long.parseLong(value.trim());
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private static Instant parseEpochSeconds(HttpHeaders headers, String name) {
        Long epoch = parseLong(headers, name);
        return epoch == null ? null : Instant.ofEpochSecond(epoch);
    }
}
