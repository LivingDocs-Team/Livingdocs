package com.livingdocs.github.dto;

import java.util.List;
import java.util.UUID;

/** Search hits from a repository's analyzed documentation and linked code entities. */
public record DocumentationSearchResponse(String query, int total, List<SearchResult> results) {
    public DocumentationSearchResponse {
        results = results == null ? List.of() : List.copyOf(results);
    }

    public record SearchResult(
            String id,
            String type,
            String title,
            String summary,
            UUID repositoryId,
            String repositoryName,
            String path,
            String language,
            Integer line,
            String url,
            int score) { }
}



