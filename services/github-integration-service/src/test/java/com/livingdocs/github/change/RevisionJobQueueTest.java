package com.livingdocs.github.change;

import com.livingdocs.github.entity.SourceChange;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.OffsetDateTime;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class RevisionJobQueueTest {
    private final OffsetDateTime now = OffsetDateTime.parse("2026-11-20T08:00:00Z");
    private final SourceChangeRequest request = new SourceChangeRequest(
            UUID.randomUUID(), SourceChange.Trigger.COMMIT, "a".repeat(40), null);
    private JdbcTemplate jdbc;
    private RevisionJobQueue queue;
    private TransactionTemplate transaction;

    @BeforeEach
    void setup() {
        JdbcDataSource db = new JdbcDataSource();
        db.setURL("jdbc:h2:mem:" + UUID.randomUUID() + ";MODE=PostgreSQL;DB_CLOSE_DELAY=-1");
        jdbc = new JdbcTemplate(db);
        jdbc.execute("CREATE TABLE repositories (id UUID PRIMARY KEY)");
        jdbc.update("INSERT INTO repositories (id) VALUES (?)", request.repositoryId());
        new ResourceDatabasePopulator(new ClassPathResource("db/migration-common/V13__revision_jobs.sql")).execute(db);
        queue = new RevisionJobQueue(jdbc);
        transaction = new TransactionTemplate(new DataSourceTransactionManager(db));
    }

    @Test
    void rollsBackWithIngestionAndDeduplicatesCommittedEvents() {
        transaction.executeWithoutResult(status -> {
            queue.enqueue(request, now);
            status.setRollbackOnly();
        });
        assertThat(queue.claim(now)).isEmpty();
        transaction.executeWithoutResult(status -> {
            queue.enqueue(request, now);
            queue.enqueue(request, now);
        });

        var restartedQueue = new RevisionJobQueue(jdbc);
        var lease = restartedQueue.claim(now).orElseThrow();
        assertThat(lease.request()).isEqualTo(request);
        assertThat(queue.claim(now)).isEmpty();
        restartedQueue.finish(lease, now, null, false);
        assertThat(status()).isEqualTo("COMPLETED");
    }

    @Test
    void expiredLeaseCanBeReclaimedAndItsPreviousWorkerCannotFinishIt() {
        queue.enqueue(request, now);
        var expired = queue.claim(now).orElseThrow();
        var later = now.plusMinutes(16);
        var replacement = queue.claim(later).orElseThrow();

        queue.finish(expired, later, null, false);
        assertThat(status()).isEqualTo("RUNNING");
        assertThat(replacement.attempt()).isEqualTo(2);
        queue.finish(replacement, later, null, false);
        assertThat(status()).isEqualTo("COMPLETED");
    }

    @Test
    void heartbeatExtendsLeaseBeyondOriginalFifteenMinutes() {
        queue.enqueue(request, now);
        var lease = queue.claim(now).orElseThrow();
        var secondWorker = new RevisionJobQueue(jdbc);

        assertThat(queue.renew(lease, now.plusMinutes(14))).contains(now.plusMinutes(29));
        assertThat(secondWorker.claim(now.plusMinutes(16))).isEmpty();
        queue.finish(lease, now.plusMinutes(16), null, false);
        assertThat(status()).isEqualTo("COMPLETED");
    }

    @Test
    void replacementFencesExpiredWorkerEvenWhileItTriesToCommit() {
        queue.enqueue(request, now);
        var old = queue.claim(now).orElseThrow();
        var later = now.plusMinutes(15);
        var secondWorker = new RevisionJobQueue(jdbc);
        var replacement = secondWorker.claim(later).orElseThrow();

        assertThat(queue.renew(old, later)).isEmpty();
        var deadline = secondWorker.renew(replacement, later).orElseThrow();
        transaction.executeWithoutResult(status -> {
            assertThat(queue.lockCurrentLease(old, later, deadline)).isFalse();
            assertThat(secondWorker.lockCurrentLease(replacement, later, deadline)).isTrue();
        });
        assertThat(secondWorker.renew(replacement, deadline)).isEmpty();
    }

    @Test
    void retryableFailuresBackOffAndStopAfterFourthAttempt() {
        var attemptTime = now;
        queue.enqueue(request, now);
        for (int attempt = 1; attempt <= 4; attempt++) {
            var lease = queue.claim(attemptTime).orElseThrow();
            assertThat(lease.attempt()).isEqualTo(attempt);
            queue.finish(lease, attemptTime, "ANALYZER_UNAVAILABLE", true);
            assertThat(queue.claim(attemptTime)).isEmpty();
            attemptTime = attemptTime.plusSeconds(60);
        }
        assertThat(status()).isEqualTo("FAILED");
        assertThat(queue.claim(attemptTime)).isEmpty();
        assertThat(jdbc.queryForObject("SELECT error_code FROM revision_jobs", String.class))
                .isEqualTo("ANALYZER_UNAVAILABLE");
    }

    private String status() {
        return jdbc.queryForObject("SELECT status FROM revision_jobs", String.class);
    }
}
