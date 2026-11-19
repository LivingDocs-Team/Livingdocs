package com.livingdocs.github.change;

import com.livingdocs.github.entity.SourceChange;

import java.util.UUID;

/**
 * LD-118/LD-119: yêu cầu phát hiện thay đổi cho một commit hoặc commit head của một Pull Request.
 * IngestionService phát event này khi webhook mang tới commit mới trên nhánh mặc định
 * hoặc Pull Request đang mở có commit head mới.
 */
public record SourceChangeRequest(UUID repositoryId, SourceChange.Trigger trigger, String commitSha,
                                  Integer pullRequestNumber) {
}
