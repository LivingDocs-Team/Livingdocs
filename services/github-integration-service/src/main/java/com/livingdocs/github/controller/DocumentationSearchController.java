package com.livingdocs.github.controller;

import java.util.UUID;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.livingdocs.github.dto.DocumentationSearchResponse;
import com.livingdocs.github.service.DocumentationSearchService;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

import static com.livingdocs.github.controller.GitHubConnectionController.USER_HEADER;

@RestController
@Tag(name = "Documentation Search", description = "Search repository documentation and linked code entities")
public class DocumentationSearchController {
    private final DocumentationSearchService searchService;

    public DocumentationSearchController(DocumentationSearchService searchService) {
        this.searchService = searchService;
    }

    @GetMapping(path = "/api/repositories/{id}/documentation/search", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "Search analyzed documentation and code entities in an authorized repository")
    public DocumentationSearchResponse search(@RequestHeader(USER_HEADER) String userId,
            @PathVariable UUID id, @RequestParam("q") String query) {
        return searchService.search(userId, id, query);
    }
}
