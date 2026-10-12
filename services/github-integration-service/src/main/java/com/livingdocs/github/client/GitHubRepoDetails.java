package com.livingdocs.github.client;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.time.Instant;

/** Thông tin chi tiết một repository: GET /repos/{owner}/{repo}. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record GitHubRepoDetails(
        Long id,
        String name,
        @JsonProperty("full_name") String fullName,
        Owner owner,
        String description,
        @JsonProperty("private") boolean privateRepo,
        boolean archived,
        boolean disabled,
        @JsonProperty("default_branch") String defaultBranch,
        @JsonProperty("html_url") String htmlUrl,
        String language,
        Long size,
        @JsonProperty("pushed_at") Instant pushedAt) {

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Owner(String login) {
    }
}
