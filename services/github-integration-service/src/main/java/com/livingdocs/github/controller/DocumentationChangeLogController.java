package com.livingdocs.github.controller;

import com.livingdocs.github.dto.DocumentationChangeLogResponse;
import com.livingdocs.github.entity.ChangeTriggerSource;
import com.livingdocs.github.service.DocumentationChangeLogService;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.Locale;

@RestController
@RequestMapping("/api/documentation")
public class DocumentationChangeLogController {

    private final DocumentationChangeLogService changeLogService;

    public DocumentationChangeLogController(DocumentationChangeLogService changeLogService) {
        this.changeLogService = changeLogService;
    }

    @GetMapping("/{docId}/change-log")
    public List<DocumentationChangeLogResponse> getChangeLog(
            @PathVariable String docId,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String triggerSource
    ) {
        ChangeTriggerSource parsedTrigger = null;
        if (triggerSource != null && !triggerSource.isBlank()) {
            try {
                parsedTrigger = ChangeTriggerSource.valueOf(triggerSource.trim().toUpperCase(Locale.ROOT));
            } catch (IllegalArgumentException ex) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "Unsupported triggerSource: " + triggerSource
                );
            }
        }
        return changeLogService.getTimeline(docId, status, parsedTrigger);
    }
}