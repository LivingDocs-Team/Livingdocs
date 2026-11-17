package com.livingdocs.github.sync;

import java.time.Instant;

/** Lỗi khi đồng bộ repository. GlobalExceptionHandler chuyển lỗi này thành JSON + mã HTTP phù hợp. */
public class RepositorySyncException extends RuntimeException {

    private final SyncErrorCode code;
    private final Instant retryAt;

    public RepositorySyncException(SyncErrorCode code, String message) {
        this(code, message, null, null);
    }

    public RepositorySyncException(SyncErrorCode code, String message, Instant retryAt, Throwable cause) {
        super(message, cause);
        this.code = code;
        this.retryAt = retryAt;
    }

    public SyncErrorCode getCode() {
        return code;
    }

    /** Thời điểm nên thử lại (chỉ có khi RATE_LIMITED và GitHub cho biết). */
    public Instant getRetryAt() {
        return retryAt;
    }
}
