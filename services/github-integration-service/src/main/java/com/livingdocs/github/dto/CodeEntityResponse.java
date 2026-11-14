package com.livingdocs.github.dto;

import com.livingdocs.github.entity.CodeEntity;

import java.util.UUID;

public record CodeEntityResponse(UUID id, String entityType, String name, String path,
                                 Integer lineStart, Integer lineEnd, String sourceUrl,
                                 String sourceCommit) {
    public static CodeEntityResponse from(CodeEntity entity) {
        return new CodeEntityResponse(entity.getId(), entity.getEntityType(), entity.getName(),
                entity.getPath(), entity.getLineStart(), entity.getLineEnd(), entity.getSourceUrl(),
                entity.getSourceCommit());
    }
}



