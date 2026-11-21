package com.livingdocs.github.controller;

import com.livingdocs.github.dto.DocumentationChangeLogResponse;
import com.livingdocs.github.entity.ChangeTriggerSource;
import com.livingdocs.github.service.DocumentAccessService;
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
    private final DocumentAccessService documentAccessService;

    public DocumentationChangeLogController(DocumentationChangeLogService changeLogService,
                                            DocumentAccessService documentAccessService) {
        this.changeLogService = changeLogService;
        this.documentAccessService = documentAccessService;
    }

    /**
     * LD-177 P1: trước khi trả timeline, kiểm tra quyền đọc tài liệu của caller
     * (cùng logic với DocumentWorkflowController) để không lộ metadata changelog
     * cho user ngoài phạm vi chỉ vì biết docId.
     */
    @GetMapping("/{docId}/change-log")
    public List<DocumentationChangeLogResponse> getChangeLog(
            @PathVariable String docId,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String triggerSource,
            @RequestHeader(value = "X-User-Id", required = false) String callerUserId
    ) {
        if (callerUserId == null || callerUserId.isBlank()) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED,
                    "Caller identity is required");
        }
        if (!documentAccessService.canReadDocument(callerUserId, docId)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                    "Caller does not have read access to this document");
        }

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