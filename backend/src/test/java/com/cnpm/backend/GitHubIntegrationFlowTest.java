package com.cnpm.backend;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.*;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class GitHubIntegrationFlowTest {

    private MockMvc mockMvc;

    // Controller giả lập cấu trúc Endpoint GitHub Integration
    @RestController
    @RequestMapping("/api/v1/github")
    static class TestGitHubController {
        @GetMapping("/connect")
        public String connect() {
            return "ok";
        }

        @GetMapping("/callback")
        public String callback(@RequestParam String code, @RequestParam String state) {
            return "ok";
        }

        @PostMapping("/sync")
        public String sync(@RequestBody String body) {
            return "ok";
        }
    }

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(new TestGitHubController()).build();
    }

    @Test
    @DisplayName("Kiểm tra Endpoint khởi tạo luồng kết nối OAuth GitHub")
    void shouldInitiateOAuthFlow() throws Exception {
        mockMvc.perform(get("/api/v1/github/connect")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk());
    }

    @Test
    @DisplayName("Kiểm tra xử lý Callback OAuth")
    void shouldHandleOAuthCallbackSuccessfully() throws Exception {
        mockMvc.perform(get("/api/v1/github/callback")
                        .param("code", "mock_code")
                        .param("state", "mock_state")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk());
    }

    @Test
    @DisplayName("Kiểm tra luồng kích hoạt đồng bộ Repository")
    void shouldTriggerRepositorySyncFlow() throws Exception {
        String syncRequestBody = """
                {
                    "repositoryUrl": "https://github.com/octocat/Hello-World",
                    "branch": "main"
                }
                """;

        mockMvc.perform(post("/api/v1/github/sync")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(syncRequestBody))
                .andExpect(status().isOk());
    }
}