package com.livingdocs.github.client;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/** Một Pull Request: GET /repos/{owner}/{repo}/pulls/{number} (LD-146). */
@JsonIgnoreProperties(ignoreUnknown = true)
public record GitHubPullRequest(
        Integer number,
        String title,
        String body,
        String state,
        @JsonProperty("html_url") String htmlUrl,
        Account user,
        Ref head,
        Ref base) {

    /** Nhánh và commit của một phía PR: head = nhánh có thay đổi, base = nhánh sẽ merge vào. */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Ref(String ref, String sha) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Account(String login) {
    }
}
