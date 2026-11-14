package com.livingdocs.github.client;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Một file thay đổi: phần tử "files" của GET /repos/{owner}/{repo}/commits/{sha},
 * hoặc của GET /repos/{owner}/{repo}/pulls/{number}/files (cùng dạng JSON).
 *
 * @param status added, removed, modified, renamed, copied, changed hoặc unchanged
 * @param sha    SHA của blob sau thay đổi
 * @param patch  unified diff của file; GitHub bỏ trống với file nhị phân hoặc diff quá lớn
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record GitHubChangedFile(
        String filename,
        String status,
        @JsonProperty("previous_filename") String previousFilename,
        String sha,
        Integer additions,
        Integer deletions,
        String patch) {
}



