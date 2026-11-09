package com.cnpm.backend.controller;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import com.cnpm.backend.service.GitHubOAuthService;

import java.util.Map;

@RestController
@RequestMapping("/api/v1/auth/github")
public class GitHubOAuthController {

    private final GitHubOAuthService gitHubOAuthService;

    public GitHubOAuthController(GitHubOAuthService gitHubOAuthService) {
        this.gitHubOAuthService = gitHubOAuthService;
    }

    @GetMapping("/callback")
    public ResponseEntity<?> handleGitHubCallback(@RequestParam("code") String code) {
        Object response = gitHubOAuthService.processOAuthCallback(code);
        return ResponseEntity.ok(response);
    }

    // Xử lý exception trả về HTTP 400 Bad Request cho test case lỗi
    @ExceptionHandler(RuntimeException.class)
    public ResponseEntity<?> handleException(RuntimeException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(Map.of("message", ex.getMessage()));
    }
}