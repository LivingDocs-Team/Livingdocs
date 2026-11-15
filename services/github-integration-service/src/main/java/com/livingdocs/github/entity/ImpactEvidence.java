package com.livingdocs.github.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

/** LD-126: một chỗ trong phần tài liệu nhắc tới code đã thay đổi (bảng source_change_document_evidence). */
@Embeddable
public class ImpactEvidence {

    @Column(nullable = false, length = 500)
    private String target;

    /** name, path, module, line_ref, parameter... (theo ai-service, LD-148). */
    @Column(length = 30)
    private String kind;

    @Column(name = "line_number", nullable = false)
    private int line;

    @Column(nullable = false, length = 300)
    private String excerpt;

    protected ImpactEvidence() {
    }

    public ImpactEvidence(String target, String kind, int line, String excerpt) {
        this.target = cut(target, 500);
        this.kind = cut(kind, 30);
        this.line = line;
        this.excerpt = cut(excerpt, 300);
    }

    private static String cut(String value, int max) {
        return value != null && value.length() > max ? value.substring(0, max) : value;
    }

    public String getTarget() { return target; }

    public String getKind() { return kind; }

    public int getLine() { return line; }

    public String getExcerpt() { return excerpt; }
}
