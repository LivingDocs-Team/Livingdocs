package com.livingdocs.github.change;

/**
 * LD-120: một code entity do Code Analyzer tìm thấy trong một file.
 *
 * @param kind      CLASS, INTERFACE, ENUM, RECORD, ANNOTATION, METHOD, FUNCTION hoặc ENDPOINT
 * @param name      tên đầy đủ trong file, ví dụ "RepositorySyncService.sync" hoặc "GET /api/repositories"
 * @param startLine dòng đầu (tính từ 1)
 * @param endLine   dòng cuối (gồm cả dòng này)
 */
public record CodeEntity(String kind, String name, int startLine, int endLine) {

    /** Hai entity cùng loại và cùng tên được coi là một (ví dụ cùng method ở bản trước và bản sau). */
    String key() {
        return kind + " " + name;
    }
}



