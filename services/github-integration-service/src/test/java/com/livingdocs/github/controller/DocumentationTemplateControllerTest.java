package com.livingdocs.github.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.dto.DocumentationTemplateRequest;
import com.livingdocs.github.service.DocumentationTemplateService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.List;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class DocumentationTemplateControllerTest {

    private static final ObjectMapper JSON = new ObjectMapper();

    @Mock
    private DocumentationTemplateService templateService;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        MockitoAnnotations.openMocks(this);
        mockMvc = MockMvcBuilders.standaloneSetup(
                new DocumentationTemplateController(templateService)).build();
    }

    @Test
    void listsTemplatesAndSections() throws Exception {
        when(templateService.list()).thenReturn(JSON.readTree("[{\"id\":\"default\",\"built_in\":true}]"));
        when(templateService.sections()).thenReturn(JSON.readTree("{\"sections\":[\"Overview\"]}"));

        mockMvc.perform(get("/api/documentation/templates"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value("default"));
        mockMvc.perform(get("/api/documentation/templates/sections"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sections[0]").value("Overview"));
    }

    @Test
    void createsUpdatesAndDeletesCustomTemplate() throws Exception {
        DocumentationTemplateRequest body = new DocumentationTemplateRequest(
                "Onboarding", "For new members", "Short.", List.of("Overview", "Functions"));
        String json = """
                {"name":"Onboarding","description":"For new members","instructions":"Short.",
                 "sections":["Overview","Functions"]}
                """;
        when(templateService.create(body)).thenReturn(JSON.readTree("{\"id\":\"a1b2c3d4\"}"));
        when(templateService.update("a1b2c3d4", body)).thenReturn(JSON.readTree("{\"id\":\"a1b2c3d4\"}"));

        mockMvc.perform(post("/api/documentation/templates")
                        .contentType(MediaType.APPLICATION_JSON).content(json))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value("a1b2c3d4"));
        mockMvc.perform(put("/api/documentation/templates/a1b2c3d4")
                        .contentType(MediaType.APPLICATION_JSON).content(json))
                .andExpect(status().isOk());
        mockMvc.perform(delete("/api/documentation/templates/a1b2c3d4"))
                .andExpect(status().isNoContent());

        verify(templateService).delete("a1b2c3d4");
    }
}
