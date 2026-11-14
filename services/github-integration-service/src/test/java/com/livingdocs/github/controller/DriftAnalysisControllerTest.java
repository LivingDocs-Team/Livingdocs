package com.livingdocs.github.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.dto.DriftAnalysisRequest;
import com.livingdocs.github.service.DriftAnalysisService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.List;
import java.util.UUID;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** LD-150: HTTP API của phân tích lệch tài liệu thủ công (LD-145). */
class DriftAnalysisControllerTest {

    private static final UUID REPOSITORY_ID = UUID.fromString("22222222-2222-2222-2222-222222222222");
    private static final ObjectMapper JSON = new ObjectMapper();

    @Mock
    private DriftAnalysisService driftService;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        MockitoAnnotations.openMocks(this);
        mockMvc = MockMvcBuilders.standaloneSetup(new DriftAnalysisController(driftService)).build();
    }

    @Test
    void analyzeReturnsCreatedReport() throws Exception {
        DriftAnalysisRequest request = new DriftAnalysisRequest(7, List.of("doc-1"), false);
        when(driftService.analyzePullRequest("user-1", REPOSITORY_ID, request)).thenReturn(JSON.readTree("""
                {"id":"report-1","status":"drift_detected","summary":{"findings":2,"highest_severity":"high"}}
                """));

        mockMvc.perform(post("/api/repositories/" + REPOSITORY_ID + "/drift/analyze")
                        .header("X-User-Id", "user-1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"pullRequestNumber":7,"documentIds":["doc-1"],"includeRepositoryDocs":false}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value("report-1"))
                .andExpect(jsonPath("$.summary.highest_severity").value("high"));

        verify(driftService).analyzePullRequest("user-1", REPOSITORY_ID, request);
    }

    @Test
    void analyzeRequiresUserHeader() throws Exception {
        mockMvc.perform(post("/api/repositories/" + REPOSITORY_ID + "/drift/analyze")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"pullRequestNumber\":7}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void listsReportsOfRepositoryAndReadsOneReport() throws Exception {
        when(driftService.listReports("user-1", REPOSITORY_ID, 7)).thenReturn(JSON.readTree("""
                [{"id":"report-1","status":"no_drift"}]
                """));
        when(driftService.getReport("user-1", "report-1")).thenReturn(JSON.readTree("""
                {"id":"report-1","status":"no_drift","findings":[]}
                """));

        mockMvc.perform(get("/api/repositories/" + REPOSITORY_ID + "/drift/reports")
                        .header("X-User-Id", "user-1").param("pullRequest", "7"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value("report-1"));
        mockMvc.perform(get("/api/drift/reports/report-1").header("X-User-Id", "user-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("no_drift"));
    }

    @Test
    void repositoryScopedReportMarkdownAndSeverityRules() throws Exception {
        when(driftService.getReport("user-1", REPOSITORY_ID, "report-1", "high")).thenReturn(JSON.readTree("""
                {"id":"report-1","summary":{"highest_severity":"critical"},"findings":[]}
                """));
        when(driftService.getReportMarkdown("user-1", REPOSITORY_ID, "report-1", null))
                .thenReturn("## Documentation drift");
        when(driftService.severityRules()).thenReturn(JSON.readTree("""
                {"levels":[{"level":"critical","min_score":75}],"rules":[]}
                """));

        mockMvc.perform(get("/api/repositories/" + REPOSITORY_ID + "/drift/reports/report-1")
                        .header("X-User-Id", "user-1").param("minSeverity", "high"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.summary.highest_severity").value("critical"));
        mockMvc.perform(get("/api/repositories/" + REPOSITORY_ID + "/drift/reports/report-1/markdown")
                        .header("X-User-Id", "user-1"))
                .andExpect(status().isOk())
                .andExpect(content().string("## Documentation drift"));
        mockMvc.perform(get("/api/documentation/drift/severity-rules").header("X-User-Id", "user-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.levels[0].min_score").value(75));
    }
}



