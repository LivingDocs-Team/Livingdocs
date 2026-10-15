package com.livingdocs.github.client;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.time.Instant;

/** Một commit: GET /repos/{owner}/{repo}/commits/{ref} hoặc phần tử của GET .../commits. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record GitHubCommit(
        String sha,
        @JsonProperty("html_url") String htmlUrl,
        Detail commit,
        Account author) {

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Detail(String message, Person author, Person committer, TreeRef tree) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Person(String name, String email, Instant date) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record TreeRef(String sha) {
    }

    /** Tài khoản GitHub của tác giả (có thể null nếu email commit không gắn với tài khoản nào). */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Account(String login) {
    }
}
