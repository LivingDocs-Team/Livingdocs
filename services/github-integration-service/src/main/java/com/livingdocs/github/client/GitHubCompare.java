package com.livingdocs.github.client;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Kết quả so sánh 2 commit: GET /repos/{owner}/{repo}/compare/{base}...{head}.
 * Chỉ dùng merge base: diff của Pull Request được tính từ commit này, không phải từ đầu nhánh base.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record GitHubCompare(@JsonProperty("merge_base_commit") CommitRef mergeBaseCommit) {

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record CommitRef(String sha) {
    }
}



