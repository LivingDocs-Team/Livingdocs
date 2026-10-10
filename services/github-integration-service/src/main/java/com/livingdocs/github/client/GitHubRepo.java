package com.livingdocs.github.client;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(ignoreUnknown = true)
public record GitHubRepo(
        Long id,
        @JsonProperty("full_name") String fullName,
        @JsonProperty("private") boolean privateRepo,
        @JsonProperty("default_branch") String defaultBranch,
        @JsonProperty("html_url") String htmlUrl) {
}
