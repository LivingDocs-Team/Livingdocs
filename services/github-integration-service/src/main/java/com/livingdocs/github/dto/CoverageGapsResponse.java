package com.livingdocs.github.dto;

import java.util.List;
import java.util.UUID;

/** Which code entities of a repository have no documentation linked to them. */
public record CoverageGapsResponse(UUID repositoryId, long totalEntities, long documentedEntities,
                                   List<CodeEntityResponse> gaps) {
}
