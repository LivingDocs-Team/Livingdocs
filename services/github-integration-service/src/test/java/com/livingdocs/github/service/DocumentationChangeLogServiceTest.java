package com.livingdocs.github.service;

import com.livingdocs.github.dto.DocumentationChangeLogResponse;
import com.livingdocs.github.entity.ChangeTriggerSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Set;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@ActiveProfiles("test")
@Transactional
class DocumentationChangeLogServiceTest {

    @Autowired
    private DocumentationChangeLogService changeLogService;

    @Test
    void shouldRecordFilterAndResolvePrimaryRole() {
        String docId = "doc-" + UUID.randomUUID();
        UUID repoId = UUID.randomUUID();

        changeLogService.recordChange(
                docId, repoId, 1, "CREATED", "Initial AI generation",
                "u-1", "Alice", Set.of("ROLE_DEVELOPER", "ROLE_MANAGER"),
                ChangeTriggerSource.AI_GENERATION, "DRAFT", "job-001"
        );

        changeLogService.recordChange(
                docId, repoId, 2, "ROLLED_BACK", "Rollback to version 1",
                "u-2", "Bob", Set.of("ROLE_ADMIN"),
                ChangeTriggerSource.ROLLBACK, "PENDING_STAFF_REVIEW", "v1"
        );

        List<DocumentationChangeLogResponse> all = changeLogService.getTimeline(docId, null, null);
        assertEquals(2, all.size());
        assertEquals("ADMINISTRATOR", all.get(0).actorRole());
        assertEquals("MANAGER", all.get(1).actorRole());

        List<DocumentationChangeLogResponse> filtered = changeLogService.getTimeline(
                docId, "PENDING_STAFF_REVIEW", ChangeTriggerSource.ROLLBACK
        );
        assertEquals(1, filtered.size());
        assertEquals("ROLLED_BACK", filtered.get(0).action());
    }
}