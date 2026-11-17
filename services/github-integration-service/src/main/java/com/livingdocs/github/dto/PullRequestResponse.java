package com.livingdocs.github.dto;

import com.livingdocs.github.entity.RepositoryPullRequest;

import java.time.Instant;

/** LD-68: một Pull Request đã nhận, trả cho màn hình "PR & Commit List". */
public record PullRequestResponse(
        Integer number,
        String title,
        String state,
        boolean merged,
        String authorLogin,
        String headRef,
        String headSha,
        String baseRef,
        String htmlUrl,
        Instant createdAt,
        Instant updatedAt,
        Instant mergedAt,
        String source) {

    public static PullRequestResponse from(RepositoryPullRequest p) {
        return new PullRequestResponse(p.getNumber(), p.getTitle(), p.getState(), p.getMergedAt() != null,
                p.getAuthorLogin(), p.getHeadRef(), p.getHeadSha(), p.getBaseRef(), p.getHtmlUrl(),
                p.getCreatedAt(), p.getUpdatedAt(), p.getMergedAt(), p.getSource().name());
    }
}
