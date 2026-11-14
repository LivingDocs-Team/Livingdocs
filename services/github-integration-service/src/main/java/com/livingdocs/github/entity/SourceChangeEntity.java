package com.livingdocs.github.entity;

import com.livingdocs.github.change.ChangedEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

/** LD-120: một code entity thay đổi trong file (bảng source_change_entities). */
@Embeddable
public class SourceChangeEntity {

    private static final int MAX_NAME_LENGTH = 500;

    @Column(nullable = false, length = 20)
    private String kind;

    @Column(nullable = false, length = MAX_NAME_LENGTH)
    private String name;

    /** ADDED, MODIFIED hoặc REMOVED. */
    @Column(name = "change_type", nullable = false, length = 20)
    private String changeType;

    @Column(name = "start_line", nullable = false)
    private int startLine;

    @Column(name = "end_line", nullable = false)
    private int endLine;

    protected SourceChangeEntity() {
    }

    public SourceChangeEntity(ChangedEntity entity) {
        this.kind = entity.kind();
        this.name = entity.name().length() > MAX_NAME_LENGTH ? entity.name().substring(0, MAX_NAME_LENGTH) : entity.name();
        this.changeType = entity.change();
        this.startLine = entity.startLine();
        this.endLine = entity.endLine();
    }

    public String getKind() { return kind; }
    public String getName() { return name; }
    public String getChangeType() { return changeType; }
    public int getStartLine() { return startLine; }
    public int getEndLine() { return endLine; }
}



