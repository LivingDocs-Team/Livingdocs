package com.livingdocs.github.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.livingdocs.github.dto.DocumentationGenerationRequest;
import com.livingdocs.github.service.DocumentationGenerationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

import static com.livingdocs.github.controller.GitHubConnectionController.USER_HEADER;

@RestController
@Tag(name = "Documentation Generation", description = "Repository analysis and AI documentation orchestration")
public class DocumentationGenerationController {

    private final DocumentationGenerationService generationService;

    public DocumentationGenerationController(DocumentationGenerationService generationService) {
        this.generationService = generationService;
    }

    @PostMapping(path = "/api/repositories/{id}/documentation/generate",
            consumes = MediaType.APPLICATION_JSON_VALUE, produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "Analyze a synchronized repository and start documentation generation")
    public ResponseEntity<JsonNode> generate(
            @RequestHeader(USER_HEADER) String userId,
            @PathVariable UUID id,
            @RequestBody(required = false) DocumentationGenerationRequest request) {
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .body(generationService.generate(userId, id, request));
    }

    @GetMapping(path = "/api/documentation/jobs/{jobId}", produces = MediaType.APPLICATION_JSON_VALUE)
    public JsonNode getJob(@RequestHeader(USER_HEADER) String userId, @PathVariable String jobId) {
        return generationService.getJob(userId, jobId);
    }

    @GetMapping(path = "/api/documentation/jobs/{jobId}/result", produces = "text/markdown")
    public ResponseEntity<String> getResult(
            @RequestHeader(USER_HEADER) String userId, @PathVariable String jobId) {
        return ResponseEntity.ok().contentType(MediaType.parseMediaType("text/markdown"))
                .body(generationService.getResult(userId, jobId));
    }

    @GetMapping(path = "/api/documentation/jobs/{jobId}/report", produces = MediaType.APPLICATION_JSON_VALUE)
    public JsonNode getReport(@RequestHeader(USER_HEADER) String userId, @PathVariable String jobId) {
        return generationService.getReport(userId, jobId);
    }
}
