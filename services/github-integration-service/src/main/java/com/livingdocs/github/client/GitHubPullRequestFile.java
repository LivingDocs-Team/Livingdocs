package com.livingdocs.github.client;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Một file thay đổi trong Pull Request: phần tử của GET /repos/{owner}/{repo}/pulls/{number}/files.
 *
 * @param sha              blob SHA của file ở commit head (null / không dùng khi file bị xoá)
 * @param status           added | removed | modified | renamed | copied | changed | unchanged
 * @param patch            unified diff của file; GitHub bỏ trống với file nhị phân hoặc diff quá lớn
 * @param previousFilename tên cũ khi file được đổi tên / di chuyển
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record GitHubPullRequestFile(
        String sha,
        String filename,
        String status,
        Integer additions,
        Integer deletions,
        Integer changes,
        String patch,
        @JsonProperty("previous_filename") String previousFilename) {
}



