package com.livingdocs.github.exception;

/** Lỗi khi gọi GitHub API. unauthorized = true nghĩa là token đã hỏng (401). */
public class GitHubApiException extends RuntimeException {

    private final boolean unauthorized;

    public GitHubApiException(String message, boolean unauthorized) {
        super(message);
        this.unauthorized = unauthorized;
    }

    public GitHubApiException(String message, Throwable cause) {
        super(message, cause);
        this.unauthorized = false;
    }

    public boolean isUnauthorized() { return unauthorized; }
}
