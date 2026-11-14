package com.livingdocs.github.dto;

import java.util.List;

/**
 * Yêu cầu phân tích lệch tài liệu thủ công cho một Pull Request (LD-145).
 *
 * @param pullRequestNumber     số của Pull Request trên GitHub (bắt buộc, >= 1)
 * @param documentIds           tài liệu đã lưu cần kiểm tra; bỏ trống = mọi tài liệu của repo này
 * @param includeRepositoryDocs có kiểm tra cả file Markdown trong repo (README, docs/...) không; mặc định có
 */
public record DriftAnalysisRequest(Integer pullRequestNumber, List<String> documentIds,
                                   Boolean includeRepositoryDocs) {
}



