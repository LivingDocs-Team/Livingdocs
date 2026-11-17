package com.livingdocs.github.config;

import com.livingdocs.github.client.GitHubClient;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** Frontend (cổng 3000 hoặc 5173) gọi được API từ trình duyệt; địa chỉ lạ thì bị chặn. */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(com.livingdocs.github.security.InternalServiceTestMvcConfig.class)
class CorsConfigTest {

    @Autowired MockMvc mvc;

    @MockitoBean GitHubClient gitHubClient;

    @Test
    void preflightFromFrontend_isAllowed() throws Exception {
        mvc.perform(options("/api/workspaces/ws-1/repositories")
                        .header("Origin", "http://localhost:3000")
                        .header("Access-Control-Request-Method", "POST")
                        .header("Access-Control-Request-Headers", "X-User-Id, Content-Type"))
                .andExpect(status().isOk())
                .andExpect(header().string("Access-Control-Allow-Origin", "http://localhost:3000"));
    }

    @Test
    void requestFromViteDevServer_getsCorsHeader() throws Exception {
        mvc.perform(get("/api/github/connection")
                        .header("Origin", "http://localhost:5173")
                        .header("X-User-Id", "user-cors"))
                .andExpect(status().isOk())
                .andExpect(header().string("Access-Control-Allow-Origin", "http://localhost:5173"))
                .andExpect(jsonPath("$.connected").value(false));
    }

    @Test
    void unknownOrigin_isRejected() throws Exception {
        mvc.perform(options("/api/github/connection")
                        .header("Origin", "http://evil.example.com")
                        .header("Access-Control-Request-Method", "GET"))
                .andExpect(status().isForbidden());
    }
}
