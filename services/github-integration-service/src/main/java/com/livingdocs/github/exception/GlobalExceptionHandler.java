package com.livingdocs.github.exception;

import com.livingdocs.github.dto.ErrorResponse;
import com.livingdocs.github.sync.RepositorySyncException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.dao.PessimisticLockingFailureException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingRequestHeaderException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import java.time.Duration;
import java.time.Instant;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(ApiException.class)
    public ResponseEntity<ErrorResponse> handleApi(ApiException e) {
        return build(e.getStatus(), e.getCode(), e.getMessage());
    }

    @ExceptionHandler({OptimisticLockingFailureException.class, PessimisticLockingFailureException.class})
    public ResponseEntity<ErrorResponse> handleWorkflowConcurrency(Exception e) {
        return build(HttpStatus.CONFLICT, "WORKFLOW_CONFLICT",
                "The workflow changed concurrently. Reload it and retry the action.");
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<ErrorResponse> handleConstraintConflict(DataIntegrityViolationException e) {
        return build(HttpStatus.CONFLICT, "WORKFLOW_CONFLICT",
                "The document or workflow already exists or changed concurrently.");
    }

    /** Lỗi đồng bộ repository (LD-63): mã HTTP lấy theo SyncErrorCode, kèm Retry-After khi bị rate limit. */
    @ExceptionHandler(RepositorySyncException.class)
    public ResponseEntity<ErrorResponse> handleSync(RepositorySyncException e) {
        HttpStatus status = e.getCode().httpStatus();
        ResponseEntity.BodyBuilder response = ResponseEntity.status(status);
        if (e.getRetryAt() != null) {
            long seconds = Math.max(1, Duration.between(Instant.now(), e.getRetryAt()).getSeconds());
            response.header(HttpHeaders.RETRY_AFTER, String.valueOf(seconds));
        }
        if (status.is5xxServerError()) {
            log.warn("Repository sync failed: {} - {}", e.getCode(), e.getMessage());
        }
        return response.body(new ErrorResponse(status.value(), e.getCode().name(), e.getMessage(), Instant.now()));
    }

    @ExceptionHandler(GitHubApiException.class)
    public ResponseEntity<ErrorResponse> handleGitHub(GitHubApiException e) {
        log.warn("GitHub API error: status={}, rateLimited={}, networkError={}",
                e.getStatusCode(), e.isRateLimited(), e.isNetworkError());
        String message = e.isRateLimited()
                ? "GitHub API rate limit exceeded. Please retry later."
                : e.isUnauthorized()
                        ? "GitHub authorization is no longer valid. Reconnect the account."
                        : e.isNotFound()
                                ? "The requested GitHub resource was not found."
                                : e.isNetworkError()
                                        ? "Unable to contact GitHub. Please retry later."
                                        : e.getStatusCode() > 0
                                                ? "GitHub request failed (HTTP " + e.getStatusCode() + ")."
                                                : "GitHub request failed. Please retry later.";
        return build(HttpStatus.BAD_GATEWAY, "GITHUB_API_ERROR", message);
    }

    @ExceptionHandler({MissingRequestHeaderException.class, MissingServletRequestParameterException.class})
    public ResponseEntity<ErrorResponse> handleMissing(Exception e) {
        return build(HttpStatus.BAD_REQUEST, "BAD_REQUEST", e.getMessage());
    }

    /** Body không phải JSON hợp lệ, hoặc sai kiểu dữ liệu (ví dụ "maxFiles": "abc"). */
    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ErrorResponse> handleUnreadable(HttpMessageNotReadableException e) {
        return build(HttpStatus.BAD_REQUEST, "BAD_REQUEST",
                "Body không hợp lệ: sai định dạng JSON hoặc sai kiểu dữ liệu.");
    }

    /** Tham số trên URL sai kiểu, ví dụ id repo không phải UUID. */
    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ErrorResponse> handleTypeMismatch(MethodArgumentTypeMismatchException e) {
        return build(HttpStatus.BAD_REQUEST, "BAD_REQUEST",
                "Tham số '" + e.getName() + "' không hợp lệ: " + e.getValue());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleValidation(MethodArgumentNotValidException e) {
        String message = e.getBindingResult().getFieldErrors().stream()
                .map(f -> f.getField() + ": " + f.getDefaultMessage())
                .findFirst()
                .orElse("Dữ liệu không hợp lệ");
        return build(HttpStatus.BAD_REQUEST, "VALIDATION_ERROR", message);
    }

    /**
     * Lỗi không lường trước (LD-76): trả JSON cùng định dạng với các lỗi khác thay vì trang lỗi mặc định,
     * không đưa chi tiết bên trong ra ngoài. Lỗi của Spring đã có mã 4xx riêng (sai đường dẫn, sai method...)
     * thì giữ nguyên mã đó.
     */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleUnexpected(Exception e) {
        if (e instanceof org.springframework.web.ErrorResponse springError) {
            HttpStatus status = HttpStatus.resolve(springError.getStatusCode().value());
            if (status != null && status.is4xxClientError()) {
                return build(status, status.name(), "Request failed (HTTP " + status.value() + ").");
            }
        }
        log.error("Unexpected error in GitHub Integration Service", e);
        return build(HttpStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR",
                "Unexpected error in the GitHub Integration Service. Please retry later.");
    }

    private ResponseEntity<ErrorResponse> build(HttpStatus status, String code, String message) {
        return ResponseEntity.status(status)
                .body(new ErrorResponse(status.value(), code, message, Instant.now()));
    }
}
