package com.livingdocs.github.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.livingdocs.github.dto.DriftAnalysisRequest;
import com.livingdocs.github.service.DriftAnalysisService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

import static com.livingdocs.github.controller.GitHubConnectionController.USER_HEADER;

/** LD-145: phân tích lệch tài liệu thủ công cho một Pull Request của repo đã kết nối. */
@RestController
@Tag(name = "Documentation Drift", description = "Manual documentation drift analysis of a pull request (LD-145)")
public class DriftAnalysisController {

    private final DriftAnalysisService driftService;

    public DriftAnalysisController(DriftAnalysisService driftService) {
        this.driftService = driftService;
    }

    @PostMapping(path = "/api/repositories/{id}/drift/analyze",
            consumes = MediaType.APPLICATION_JSON_VALUE, produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "Check a pull request for documentation drift",
            description = "Reads the pull request from GitHub, analyzes the changed Python/Java files at the "
                    + "merge base and head, and checks the saved documents of the repository and its Markdown "
                    + "files. Returns findings (referential / signature / semantic) with severity, confidence "
                    + "and evidence.")
    public ResponseEntity<JsonNode> analyze(
            @RequestHeader(USER_HEADER) String userId,
            @PathVariable UUID id,
            @RequestBody DriftAnalysisRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(driftService.analyzePullRequest(userId, id, request));
    }

    @GetMapping(path = "/api/repositories/{id}/drift/reports", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "Drift reports of a repository, newest first")
    public JsonNode listReports(
            @RequestHeader(USER_HEADER) String userId,
            @PathVariable UUID id,
            @RequestParam(name = "pullRequest", required = false) Integer pullRequest) {
        return driftService.listReports(userId, id, pullRequest);
    }

    @GetMapping(path = "/api/drift/reports/{reportId}", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "One drift report with findings and evidence")
    public JsonNode getReport(@RequestHeader(USER_HEADER) String userId, @PathVariable String reportId) {
        return driftService.getReport(userId, reportId);
    }

    /** LD-159: same report under the repository, so the browser reaches it through the Backend BFF. */
    @GetMapping(path = "/api/repositories/{id}/drift/reports/{reportId}", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "One drift report of a repository; minSeverity keeps findings at or above a level")
    public JsonNode getRepositoryReport(
            @RequestHeader(USER_HEADER) String userId,
            @PathVariable UUID id,
            @PathVariable String reportId,
            @RequestParam(name = "minSeverity", required = false) String minSeverity) {
        return driftService.getReport(userId, id, reportId, minSeverity);
    }

    @GetMapping(path = "/api/repositories/{id}/drift/reports/{reportId}/markdown", produces = "text/markdown")
    @Operation(summary = "The drift report as Markdown grouped by severity (pull request comment)")
    public ResponseEntity<String> getRepositoryReportMarkdown(
            @RequestHeader(USER_HEADER) String userId,
            @PathVariable UUID id,
            @PathVariable String reportId,
            @RequestParam(name = "minSeverity", required = false) String minSeverity) {
        return ResponseEntity.ok().contentType(MediaType.parseMediaType("text/markdown"))
                .body(driftService.getReportMarkdown(userId, id, reportId, minSeverity));
    }

    @GetMapping(path = "/api/documentation/drift/severity-rules", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "Severity levels (score bands, meaning, action) and the rules that set them")
    public JsonNode severityRules(@RequestHeader(USER_HEADER) String userId) {
        return driftService.severityRules();
    }
}



