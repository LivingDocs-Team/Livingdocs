package com.livingdocs.github.controller;

import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.service.DocumentationCollectionService;
import com.livingdocs.github.service.DocumentationCollectionService.Collection;
import com.livingdocs.github.service.DocumentationCollectionService.Document;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.Arrays;
import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/workspaces/{workspace}/collections")
public class DocumentationCollectionController {
    private final DocumentationCollectionService collections;

    public DocumentationCollectionController(DocumentationCollectionService collections) {
        this.collections = collections;
    }

    public record CollectionRequest(@NotBlank @Size(max = 120) String name,
                                    @Size(max = 1000) String description, UUID repositoryId) {}

    @ModelAttribute
    public void verifyAccess(@PathVariable String workspace,
            @RequestHeader("X-Verified-Workspace-Id") String verifiedWorkspace,
            @RequestHeader("X-Verified-Workspace-Access") String access,
            @RequestHeader("X-User-Authorities") String authorities,
            jakarta.servlet.http.HttpServletRequest request) {
        if (!workspace.equals(verifiedWorkspace) || !List.of("OWNER", "MEMBER").contains(access)) {
            throw ApiException.notFound("Workspace not found.");
        }
        boolean lead = isTechnicalLead(authorities);
        boolean developer = Arrays.asList(authorities.split(",")).contains("ROLE_DEVELOPER");
        if (!lead && !("GET".equals(request.getMethod()) && developer)) {
            throw ApiException.forbidden("Your role cannot perform this collection action.");
        }
    }

    private boolean isTechnicalLead(String authorities) {
        return Arrays.asList(authorities.split(",")).contains("ROLE_TECHNICAL_LEAD");
    }

    @GetMapping
    public List<Collection> list(@PathVariable String workspace) {
        return collections.list(workspace);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Collection create(@PathVariable String workspace, @Valid @RequestBody CollectionRequest request) {
        return collections.save(workspace, null, request.name(), request.description(), request.repositoryId());
    }

    @PutMapping("/{id}")
    public Collection update(@PathVariable String workspace, @PathVariable UUID id,
            @Valid @RequestBody CollectionRequest request) {
        return collections.save(workspace, id, request.name(), request.description(), request.repositoryId());
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable String workspace, @PathVariable UUID id) {
        collections.delete(workspace, id);
    }

    @GetMapping("/{id}/documents")
    public List<Document> documents(@PathVariable String workspace, @PathVariable UUID id) {
        return collections.documents(workspace, id, false);
    }

    @GetMapping("/{id}/document-candidates")
    public List<Document> candidates(@PathVariable String workspace, @PathVariable UUID id,
            @RequestHeader("X-User-Authorities") String authorities) {
        if (!isTechnicalLead(authorities)) throw ApiException.forbidden("Only a Technical Lead can browse document candidates.");
        return collections.documents(workspace, id, true);
    }

    @PutMapping("/{id}/documents/{documentId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void attach(@PathVariable String workspace, @PathVariable UUID id, @PathVariable UUID documentId) {
        collections.attach(workspace, id, documentId);
    }

    @DeleteMapping("/{id}/documents/{documentId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void detach(@PathVariable String workspace, @PathVariable UUID id, @PathVariable UUID documentId) {
        collections.detach(workspace, id, documentId);
    }

    @PutMapping("/{id}/documents/{documentId}/owner/{userId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void assign(@PathVariable String workspace, @PathVariable UUID id, @PathVariable UUID documentId,
            @PathVariable Long userId, @RequestHeader("X-Verified-Document-Owner-Id") String verifiedUserId) {
        if (userId <= 0 || !userId.toString().equals(verifiedUserId)) {
            throw ApiException.forbidden("Document owner verification is required.");
        }
        collections.assignOwner(workspace, id, documentId, userId);
    }

    @DeleteMapping("/{id}/documents/{documentId}/owner")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void clearOwner(@PathVariable String workspace, @PathVariable UUID id, @PathVariable UUID documentId) {
        collections.assignOwner(workspace, id, documentId, null);
    }
}
