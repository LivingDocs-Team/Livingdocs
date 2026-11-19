package com.livingdocs.github.client;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** Nội dung một file theo SHA: GET /repos/{owner}/{repo}/git/blobs/{sha}. content thường mã hoá base64. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record GitHubBlob(String sha, Long size, String encoding, String content) {
}
