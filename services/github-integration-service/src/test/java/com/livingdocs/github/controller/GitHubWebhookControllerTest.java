package com.livingdocs.github.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.exception.GlobalExceptionHandler;
import com.livingdocs.github.service.IngestionService;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** LD-401: service chưa cấu hình GITHUB_WEBHOOK_SECRET thì từ chối mọi webhook, không xử lý gì. */
class GitHubWebhookControllerTest {

    @Test
    void webhookSecretNotConfigured_returns503_andIgnoresPayload() throws Exception {
        IngestionService ingestionService = mock(IngestionService.class);
        MockMvc mvc = MockMvcBuilders
                .standaloneSetup(new GitHubWebhookController(ingestionService, new ObjectMapper(), ""))
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();

        mvc.perform(post(GitHubWebhookController.PATH)
                        .header("X-GitHub-Event", "push")
                        .header("X-GitHub-Delivery", "delivery-1")
                        .header("X-Hub-Signature-256", "sha256=" + "00".repeat(32))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"ref\":\"refs/heads/main\"}"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.code").value("WEBHOOK_NOT_CONFIGURED"));

        verifyNoInteractions(ingestionService);
    }
}
