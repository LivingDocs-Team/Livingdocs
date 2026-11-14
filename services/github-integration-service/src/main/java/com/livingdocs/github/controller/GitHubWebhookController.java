package com.livingdocs.github.controller;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.service.IngestionService;
import com.livingdocs.github.webhook.WebhookSignatureVerifier;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
import java.util.Map;

/**
 * LD-69/LD-70 - GitHub gọi thẳng vào đây (không qua Backend), nên xác thực bằng chữ ký
 * X-Hub-Signature-256 với GITHUB_WEBHOOK_SECRET thay cho credential nội bộ.
 */
@RestController
@Tag(name = "GitHub Webhook", description = "LD-68 - nhận event push và pull_request từ GitHub App")
public class GitHubWebhookController {

    static final String PATH = "/api/github/webhook";

    private final IngestionService ingestionService;
    private final ObjectMapper objectMapper;
    private final String webhookSecret;

    public GitHubWebhookController(IngestionService ingestionService, ObjectMapper objectMapper,
                                   @Value("${github.webhook-secret:}") String webhookSecret) {
        this.ingestionService = ingestionService;
        this.objectMapper = objectMapper;
        this.webhookSecret = webhookSecret == null ? "" : webhookSecret;
    }

    @PostMapping(PATH)
    @Operation(summary = "Webhook của GitHub App (push, pull_request)",
            description = "Trả 202 kèm status PROCESSED, DUPLICATE (cùng X-GitHub-Delivery đã xử lý) "
                    + "hoặc IGNORED (event khác, hoặc repo chưa được thêm vào workspace nào).")
    public ResponseEntity<Map<String, String>> receive(
            @RequestHeader(value = "X-GitHub-Event", required = false) String event,
            @RequestHeader(value = "X-GitHub-Delivery", required = false) String deliveryId,
            @RequestHeader(value = "X-Hub-Signature-256", required = false) String signature,
            @RequestBody byte[] body) throws IOException {
        if (webhookSecret.isBlank()) {
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "WEBHOOK_NOT_CONFIGURED",
                    "GITHUB_WEBHOOK_SECRET is not configured.");
        }
        if (!WebhookSignatureVerifier.isValid(webhookSecret, body, signature)) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "WEBHOOK_SIGNATURE_INVALID",
                    "The webhook signature is missing or invalid.");
        }
        if ("ping".equals(event)) {
            return ResponseEntity.ok(Map.of("status", "PONG"));  // GitHub gửi khi vừa lưu cấu hình webhook
        }
        if (event == null || deliveryId == null || deliveryId.isBlank()) {
            throw ApiException.badRequest("Missing X-GitHub-Event or X-GitHub-Delivery header.");
        }
        JsonNode payload;
        try {
            payload = objectMapper.readTree(body);
        } catch (JsonProcessingException e) {
            throw ApiException.badRequest("The webhook payload is not valid JSON.");
        }
        IngestionService.Result result = ingestionService.handleWebhook(deliveryId, event, payload);
        return ResponseEntity.accepted().body(Map.of("status", result.name()));
    }
}



