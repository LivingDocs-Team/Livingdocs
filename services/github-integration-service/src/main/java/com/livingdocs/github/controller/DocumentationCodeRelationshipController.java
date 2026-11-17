package com.livingdocs.github.controller;

import com.livingdocs.github.dto.CodeEntityResponse;
import com.livingdocs.github.dto.DocumentationArtifactResponse;
import com.livingdocs.github.dto.ReplaceDocumentationCodeLinksRequest;
import com.livingdocs.github.service.DocumentationCodeRelationshipService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

import static com.livingdocs.github.controller.GitHubConnectionController.USER_HEADER;

@RestController
public class DocumentationCodeRelationshipController {
    private final DocumentationCodeRelationshipService relationshipService;

    public DocumentationCodeRelationshipController(DocumentationCodeRelationshipService relationshipService) {
        this.relationshipService = relationshipService;
    }

    @GetMapping("/api/repositories/{repositoryId}/code-entities")
    public List<CodeEntityResponse> codeEntities(@RequestHeader(USER_HEADER) String userId,
            @PathVariable UUID repositoryId) {
        return relationshipService.listCodeEntities(userId, repositoryId);
    }

    @GetMapping("/api/repositories/{repositoryId}/documentation")
    public List<DocumentationArtifactResponse> documents(@RequestHeader(USER_HEADER) String userId,
            @PathVariable UUID repositoryId) {
        return relationshipService.listDocuments(userId, repositoryId);
    }

    @GetMapping("/api/documentation/{documentId}")
    public DocumentationArtifactResponse document(@RequestHeader(USER_HEADER) String userId,
            @PathVariable UUID documentId) {
        return relationshipService.getDocument(userId, documentId);
    }

    @GetMapping("/api/documentation/{documentId}/code-entities")
    public List<CodeEntityResponse> relatedCode(@RequestHeader(USER_HEADER) String userId,
            @PathVariable UUID documentId) {
        return relationshipService.relatedCode(userId, documentId);
    }

    @PutMapping("/api/documentation/{documentId}/code-entities")
    public List<CodeEntityResponse> replaceLinks(@RequestHeader(USER_HEADER) String userId,
            @PathVariable UUID documentId, @Valid @RequestBody ReplaceDocumentationCodeLinksRequest request) {
        return relationshipService.replaceLinks(userId, documentId, request.codeEntityIds());
    }

    @GetMapping("/api/documentation/code-entities/{entityId}/documents")
    public List<DocumentationArtifactResponse> relatedDocuments(@RequestHeader(USER_HEADER) String userId,
            @PathVariable UUID entityId) {
        return relationshipService.relatedDocuments(userId, entityId);
    }
}
