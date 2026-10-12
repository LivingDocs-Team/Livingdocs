package com.livingdocs.github.client;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.util.List;

/**
 * Cây thư mục của một commit: GET /repos/{owner}/{repo}/git/trees/{sha}?recursive=1.
 * truncated = true nghĩa là repo quá lớn, GitHub chỉ trả về một phần.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record GitHubTree(String sha, boolean truncated, List<Entry> tree) {

    /** type = "blob" (file), "tree" (thư mục) hoặc "commit" (submodule). size chỉ có với blob. */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Entry(String path, String mode, String type, String sha, Long size) {
    }
}
