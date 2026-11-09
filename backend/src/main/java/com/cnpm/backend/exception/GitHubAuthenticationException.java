package com.cnpm.backend.exception;

public class GitHubAuthenticationException extends RuntimeException {
    public GitHubAuthenticationException(String message) {
        super(message);
    }
}