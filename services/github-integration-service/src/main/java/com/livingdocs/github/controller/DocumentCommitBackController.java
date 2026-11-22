package com.livingdocs.github.controller;

import com.livingdocs.github.service.DocumentCommitBackService;
import jakarta.validation.constraints.Positive;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import java.util.Arrays;
import java.util.UUID;
import java.util.stream.Collectors;

@RestController
public class DocumentCommitBackController {
    private final DocumentCommitBackService service;

    public DocumentCommitBackController(DocumentCommitBackService service) {
        this.service = service;
    }

    @PostMapping("/api/document-workflows/{id}/versions/{version}/github-commit")
    public DocumentCommitBackService.Result commit(
            @RequestHeader(DocumentWorkflowController.USER_HEADER) String actor,
            @RequestHeader(DocumentWorkflowController.AUTHORITIES_HEADER) String authorities,
            @PathVariable UUID id, @PathVariable @Positive int version) {
        return service.commit(actor, Arrays.stream(authorities.split(",")).map(String::trim)
                .collect(Collectors.toSet()), id, version);
    }
}
