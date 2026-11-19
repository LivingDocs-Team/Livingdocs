package com.livingdocs.github.entity;

import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/** LD-117: một file mã nguồn thay đổi trong source change, kèm các code entity thay đổi (LD-120). */
@Entity
@Table(name = "source_change_files")
public class SourceChangeFile {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "source_change_id", nullable = false)
    private SourceChange sourceChange;

    @Column(nullable = false, length = 1000)
    private String path;

    @Column(name = "previous_path", length = 1000)
    private String previousPath;

    /** ADDED, MODIFIED, REMOVED hoặc RENAMED. */
    @Column(name = "change_type", nullable = false, length = 20)
    private String changeType;

    @Column(length = 20)
    private String language;

    private Integer additions;

    private Integer deletions;

    /** Vì sao không tìm entity: PATCH_UNAVAILABLE, FILE_TOO_LARGE, NOT_ANALYZED, TOO_MANY_FILES. Null là đã tìm. */
    @Column(name = "skipped_reason", length = 50)
    private String skippedReason;

    @ElementCollection
    @CollectionTable(name = "source_change_entities", joinColumns = @JoinColumn(name = "file_id"))
    private List<SourceChangeEntity> entities = new ArrayList<>();

    public UUID getId() { return id; }

    void setSourceChange(SourceChange sourceChange) { this.sourceChange = sourceChange; }

    public String getPath() { return path; }
    public void setPath(String path) { this.path = path; }

    public String getPreviousPath() { return previousPath; }
    public void setPreviousPath(String previousPath) { this.previousPath = previousPath; }

    public String getChangeType() { return changeType; }
    public void setChangeType(String changeType) { this.changeType = changeType; }

    public String getLanguage() { return language; }
    public void setLanguage(String language) { this.language = language; }

    public Integer getAdditions() { return additions; }
    public void setAdditions(Integer additions) { this.additions = additions; }

    public Integer getDeletions() { return deletions; }
    public void setDeletions(Integer deletions) { this.deletions = deletions; }

    public String getSkippedReason() { return skippedReason; }
    public void setSkippedReason(String skippedReason) { this.skippedReason = skippedReason; }

    public List<SourceChangeEntity> getEntities() { return entities; }
}
