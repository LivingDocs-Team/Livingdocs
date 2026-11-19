package com.livingdocs.github.dto;

import com.livingdocs.github.entity.ConnectedRepository;

import java.time.Instant;
import java.util.UUID;

public record RepositoryResponse(
        UUID id,
        String workspaceId,
        Long githubRepoId,
        String fullName,
        String defaultBranch,
        boolean privateRepo,
        String htmlUrl,
        String status,
        Instant lastSyncedAt,
        Instant createdAt) {

    public static RepositoryResponse from(ConnectedRepository r) {
        return new RepositoryResponse(r.getId(), r.getWorkspaceId(), r.getGithubRepoId(), r.getFullName(),
                r.getDefaultBranch(), r.isPrivateRepo(), r.getHtmlUrl(), r.getStatus().name(),
                r.getLastSyncedAt(), r.getCreatedAt());
    }
}
