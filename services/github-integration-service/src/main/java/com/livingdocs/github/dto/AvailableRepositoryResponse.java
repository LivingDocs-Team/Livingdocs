package com.livingdocs.github.dto;

/** Repo trên GitHub mà người dùng có thể thêm vào LivingDocs. */
public record AvailableRepositoryResponse(
        Long githubRepoId,
        String fullName,
        boolean privateRepo,
        String defaultBranch,
        String htmlUrl) {
}
