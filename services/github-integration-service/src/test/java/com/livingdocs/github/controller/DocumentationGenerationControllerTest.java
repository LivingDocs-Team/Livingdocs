package com.livingdocs.github.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.dto.DocumentationGenerationRequest;
import com.livingdocs.github.service.DocumentationGenerationService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.UUID;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class DocumentationGenerationControllerTest {

    private static final UUID REPOSITORY_ID = UUID.fromString("11111111-1111-1111-1111-111111111111");

    @Mock
    private DocumentationGenerationService generationService;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        MockitoAnnotations.openMocks(this);
        mockMvc = MockMvcBuilders.standaloneSetup(
                new DocumentationGenerationController(generationService)).build();
    }

    @Test
    void endpointRequiresUserHeaderAndReturnsAcceptedAiJob() throws Exception {
        when(generationService.generate("user-1", REPOSITORY_ID,
                new DocumentationGenerationRequest("default", "vi")))
                .thenReturn(new ObjectMapper().readTree("""
                        {"id":"job-123","status":"pending","target":"acme/shop"}
                        """));

        mockMvc.perform(post("/api/repositories/" + REPOSITORY_ID + "/documentation/generate")
                        .header("X-User-Id", "user-1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"templateId":"default","outputLanguage":"vi"}
                                """))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.id").value("job-123"))
                .andExpect(jsonPath("$.status").value("pending"));

        verify(generationService).generate("user-1", REPOSITORY_ID,
                new DocumentationGenerationRequest("default", "vi"));
    }
}
