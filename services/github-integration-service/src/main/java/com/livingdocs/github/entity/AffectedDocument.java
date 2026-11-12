package com.livingdocs.github.entity;

import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OrderBy;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * LD-122 / LD-124: một phần (theo file) của tài liệu đã lưu ở ai-service có thể đã cũ vì source change.
 * LD-125: DIRECT nếu phần này được sinh ra từ chính file thay đổi, DEPENDENT nếu nó mô tả code khác
 * nhưng nhắc tới entity, endpoint hoặc đường dẫn đã thay đổi.
 */
@Entity
@Table(name = "source_change_documents")
public class AffectedDocument {

    public enum Dependency { DIRECT, DEPENDENT }

    private static final int MAX_REASONS_LENGTH = 4000;

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "source_change_id", nullable = false)
    private SourceChange sourceChange;

    @Column(name = "document_id", nullable = false, length = 100)
    private String documentId;

    @Column(length = 500)
    private String title;

    private Integer version;

    @Column(name = "section_path", nullable = false, length = 1000)
    private String sectionPath;

    @Column(name = "documents_file", length = 1000)
    private String documentsFile;

    @Enumerated(EnumType.STRING)
    @JdbcTypeCode(SqlTypes.VARCHAR)
    @Column(nullable = false, length = 20)
    private Dependency dependency;

    /** Mỗi dòng một lý do, vd. "documents changed file shop/cart.py", "mentions `Invoice.total`". */
    @Column(nullable = false, length = MAX_REASONS_LENGTH)
    private String reasons;

    /** LD-126: các chỗ trong phần tài liệu nhắc tới code đã thay đổi, theo dòng. */
    @ElementCollection
    @CollectionTable(name = "source_change_document_evidence", joinColumns = @JoinColumn(name = "document_row_id"))
    @OrderBy("line")
    private List<ImpactEvidence> evidence = new ArrayList<>();

    protected AffectedDocument() {
    }

    public AffectedDocument(String documentId, String title, Integer version, String sectionPath,
                            String documentsFile, Dependency dependency, List<String> reasons,
                            List<ImpactEvidence> evidence) {
        this.documentId = cut(documentId, 100);
        this.title = cut(title, 500);
        this.version = version;
        this.sectionPath = cut(sectionPath, 1000);
        this.documentsFile = cut(documentsFile, 1000);
        this.dependency = dependency;
        this.reasons = cut(String.join("\n", reasons == null ? List.of() : reasons), MAX_REASONS_LENGTH);
        // shortcut: keeps the first 20 places only, enough to explain the impact; page them if users need all
        this.evidence.addAll(evidence == null ? List.of() : evidence.stream().limit(20).toList());
    }

    private static String cut(String value, int max) {
        return value != null && value.length() > max ? value.substring(0, max) : value;
    }

    void setSourceChange(SourceChange sourceChange) { this.sourceChange = sourceChange; }

    public String getDocumentId() { return documentId; }

    public String getTitle() { return title; }

    public Integer getVersion() { return version; }

    public String getSectionPath() { return sectionPath; }

    public String getDocumentsFile() { return documentsFile; }

    public Dependency getDependency() { return dependency; }

    public List<String> getReasons() { return reasons.isEmpty() ? List.of() : List.of(reasons.split("\n")); }

    public List<ImpactEvidence> getEvidence() { return evidence; }
}
