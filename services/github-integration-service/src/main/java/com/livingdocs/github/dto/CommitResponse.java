package com.livingdocs.github.dto;

import com.livingdocs.github.entity.RepositoryCommit;

import java.time.Instant;

/** LD-68: một commit đã nhận, trả cho màn hình "PR & Commit List". */
public record CommitResponse(
        String sha,
        String branch,
        String message,
        String authorName,
        String authorLogin,
        Instant committedAt,
        String htmlUrl,
        String source) {

    public static CommitResponse from(RepositoryCommit c) {
        return new CommitResponse(c.getSha(), c.getBranch(), c.getMessage(), c.getAuthorName(),
                c.getAuthorLogin(), c.getCommittedAt(), c.getHtmlUrl(), c.getSource().name());
    }
}



