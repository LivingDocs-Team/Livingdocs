package com.livingdocs.github.client;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.time.Instant;

/**
 * Một Pull Request: phần tử của GET /repos/{owner}/{repo}/pulls, hoặc trường "pull_request"
 * trong webhook pull_request (hai nơi có cùng dạng JSON với các trường dưới đây).
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record GitHubPullRequest(
        Integer number,
        String title,
        String state,
        @JsonProperty("html_url") String htmlUrl,
        Account user,
        Ref head,
        Ref base,
        @JsonProperty("created_at") Instant createdAt,
        @JsonProperty("updated_at") Instant updatedAt,
        @JsonProperty("closed_at") Instant closedAt,
        @JsonProperty("merged_at") Instant mergedAt) {

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Account(String login) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Ref(String ref, String sha) {
    }
}
