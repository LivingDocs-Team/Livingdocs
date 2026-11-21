package com.livingdocs.github.service;

import com.livingdocs.github.dto.DocumentationChangeLogResponse;
import com.livingdocs.github.entity.ChangeTriggerSource;
import com.livingdocs.github.entity.DocumentationChangeLog;
import com.livingdocs.github.repository.DocumentationChangeLogRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Collection;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

@Service
public class DocumentationChangeLogService {

    public List<String> findDocumentIdsByRepositoryId(UUID repositoryId) {
    System.out.println("=== WEBHOOK ĐANG LẤY DOC ID CHO REPO: " + repositoryId + " ===");
    return List.of("doc-123"); 
}

    private static final List<String> ROLE_PRIORITY = List.of(
            "ADMINISTRATOR", "ADMIN", "MANAGER", "TECHNICAL_LEAD", "STAFF", "DEVELOPER"
    );

    private final DocumentationChangeLogRepository repository;

    public DocumentationChangeLogService(DocumentationChangeLogRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public DocumentationChangeLog recordChange(
            String documentId,
            UUID repositoryId,
            Integer versionNumber,
            String action,
            String summary,
            String actorId,
            String actorName,
            Collection<String> authorities,
            ChangeTriggerSource triggerSource,
            String status,
            String referenceId
    ) {
        DocumentationChangeLog entry = new DocumentationChangeLog();
        entry.setDocumentId(documentId);
        entry.setRepositoryId(repositoryId);
        entry.setVersionNumber(versionNumber);
        entry.setAction(action);
        entry.setSummary(truncateSummary(summary));
        entry.setActorId(actorId);
        entry.setActorName(actorName != null && !actorName.isBlank() ? actorName : actorId);
        entry.setActorRole(resolvePrimaryRole(authorities));
        entry.setTriggerSource(triggerSource != null ? triggerSource : ChangeTriggerSource.MANUAL_EDIT);
        entry.setStatus(status != null && !status.isBlank() ? status.trim().toUpperCase(Locale.ROOT) : "DRAFT");
        entry.setReferenceId(referenceId);
        return repository.save(entry);
    }

    @Transactional(readOnly = true)
    public List<DocumentationChangeLogResponse> getTimeline(
            String documentId,
            String statusFilter,
            ChangeTriggerSource triggerFilter
    ) {
        String normalizedStatus = (statusFilter == null || statusFilter.isBlank())
                ? null
                : statusFilter.trim().toUpperCase(Locale.ROOT);

        List<DocumentationChangeLog> rows;
        if (normalizedStatus != null && triggerFilter != null) {
            rows = repository.findByDocumentIdAndStatusAndTriggerSourceOrderByCreatedAtDesc(
                    documentId, normalizedStatus, triggerFilter);
        } else if (normalizedStatus != null) {
            rows = repository.findByDocumentIdAndStatusOrderByCreatedAtDesc(documentId, normalizedStatus);
        } else if (triggerFilter != null) {
            rows = repository.findByDocumentIdAndTriggerSourceOrderByCreatedAtDesc(documentId, triggerFilter);
        } else {
            rows = repository.findByDocumentIdOrderByCreatedAtDesc(documentId);
        }

        return rows.stream()
                .map(DocumentationChangeLogResponse::from)
                .toList();
    }

    public String resolvePrimaryRole(Collection<String> authorities) {
        if (authorities == null || authorities.isEmpty()) {
            return "SYSTEM";
        }
        List<String> normalized = authorities.stream()
                .filter(s -> s != null && !s.isBlank())
                .map(String::trim)
                .map(a -> a.startsWith("ROLE_") ? a.substring(5) : a)
                .map(a -> a.toUpperCase(Locale.ROOT))
                .toList();

        for (String role : ROLE_PRIORITY) {
            if (normalized.contains(role)) {
                return "ADMIN".equals(role) ? "ADMINISTRATOR" : role;
            }
        }
        return normalized.isEmpty() ? "USER" : normalized.get(0);
    }

    private static String truncateSummary(String summary) {
        if (summary == null || summary.isBlank()) {
            return "Documentation updated";
        }
        String trimmed = summary.trim();
        return trimmed.length() <= 500 ? trimmed : trimmed.substring(0, 497) + "...";
    }
}