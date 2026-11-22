package com.livingdocs.github.change;

import com.livingdocs.github.entity.SourceChange.Trigger;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.service.RepositoryManagementService;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

class AutoUpdatePoliciesTest {
    @Test
    void resolvesBothTriggersWithRepositoryIsolationAndMostSpecificScope() {
        var database = new EmbeddedDatabaseBuilder().setType(EmbeddedDatabaseType.H2).generateUniqueName(true).build();
        try {
            var jdbc = new JdbcTemplate(database);
            jdbc.execute("CREATE TABLE repositories (id UUID PRIMARY KEY)");
            new ResourceDatabasePopulator(new ClassPathResource("db/migration-common/V14__auto_update_policies.sql"))
                    .execute(database);
            var repo = UUID.randomUUID();
            var other = UUID.randomUUID();
            jdbc.update("INSERT INTO repositories (id) VALUES (?), (?)", repo, other);
            jdbc.update("""
                    INSERT INTO auto_update_policies VALUES
                    (?, 'REPOSITORY', '', FALSE, FALSE),
                    (?, 'MODULE', 'src', TRUE, FALSE),
                    (?, 'MODULE', 'src/main', FALSE, TRUE),
                    (?, 'DOCUMENT', 'document-id', TRUE, TRUE)
                    """, repo, repo, repo, repo);
            var policies = new AutoUpdatePolicies(jdbc, mock(ConnectedRepositoryRepository.class),
                    mock(RepositoryManagementService.class));
            assertThat(policies.allows(repo, Trigger.COMMIT, "file", "file", "src/main/Main.java")).isFalse();
            assertThat(policies.allows(repo, Trigger.PULL_REQUEST, "file", "file", "src/main/Main.java")).isTrue();
            assertThat(policies.allows(repo, Trigger.COMMIT, "module", "module", "src")).isTrue();
            assertThat(policies.allows(repo, Trigger.PULL_REQUEST, "repo", "repository", "acme/docs")).isFalse();
            assertThat(policies.allows(repo, Trigger.COMMIT, "document-id", "file", "src/main/Main.java")).isTrue();
            assertThat(policies.allows(other, Trigger.PULL_REQUEST, "file", "file", "src/main/Main.java")).isTrue();
        } finally {
            database.shutdown();
        }
    }
}
