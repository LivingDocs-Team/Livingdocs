package com.livingdocs.github.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.livingdocs.github.dto.DocumentationTemplateRequest;
import com.livingdocs.github.service.DocumentationTemplateService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Templates users choose from when generating documentation (stored by the AI service). */
@RestController
@RequestMapping(path = "/api/documentation/templates", produces = MediaType.APPLICATION_JSON_VALUE)
@Tag(name = "Documentation Templates", description = "View and manage documentation templates")
public class DocumentationTemplateController {

    private final DocumentationTemplateService templateService;

    public DocumentationTemplateController(DocumentationTemplateService templateService) {
        this.templateService = templateService;
    }

    @GetMapping
    @Operation(summary = "List available templates: built-in first, then custom ones")
    public JsonNode list() {
        return templateService.list();
    }

    @GetMapping("/sections")
    @Operation(summary = "Sections a template may contain")
    public JsonNode sections() {
        return templateService.sections();
    }

    @GetMapping("/{templateId}")
    public JsonNode get(@PathVariable String templateId) {
        return templateService.get(templateId);
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "Create a custom template")
    public ResponseEntity<JsonNode> create(@RequestBody DocumentationTemplateRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(templateService.create(request));
    }

    @PutMapping(path = "/{templateId}", consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "Update a custom template (built-in templates are read-only)")
    public JsonNode update(@PathVariable String templateId,
            @RequestBody DocumentationTemplateRequest request) {
        return templateService.update(templateId, request);
    }

    @DeleteMapping("/{templateId}")
    @Operation(summary = "Delete a custom template")
    public ResponseEntity<Void> delete(@PathVariable String templateId) {
        templateService.delete(templateId);
        return ResponseEntity.noContent().build();
    }
}
