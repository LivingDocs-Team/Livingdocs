package com.livingdocs.github.change;

import com.livingdocs.github.entity.SourceChange;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.UUID;

@Repository
public class RevisionJobQueue {
    private static final int MAX_ATTEMPTS = 4;
    private static final Duration LEASE_DURATION = Duration.ofMinutes(15);

    private final JdbcTemplate jdbc;

    public RevisionJobQueue(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** Called inside webhook ingestion, while holding the connected repository's row lock. */
    public void enqueue(SourceChangeRequest request, OffsetDateTime now) {
        int pullRequest = request.pullRequestNumber() == null ? 0 : request.pullRequestNumber();
        jdbc.update("""
                INSERT INTO revision_jobs (id, repository_id, trigger_type, commit_sha, pr_number, status, available_at)
                SELECT ?, ?, ?, ?, ?, 'QUEUED', ?
                WHERE NOT EXISTS (SELECT 1 FROM revision_jobs
                      WHERE repository_id = ? AND trigger_type = ? AND commit_sha = ? AND pr_number = ?)
                """, UUID.randomUUID(), request.repositoryId(), request.trigger().name(), request.commitSha(),
                pullRequest, now, request.repositoryId(), request.trigger().name(), request.commitSha(), pullRequest);
    }

    public Optional<Lease> claim(OffsetDateTime now) {
        jdbc.update("""
                UPDATE revision_jobs SET status = 'FAILED', lease_token = NULL, error_code = 'LEASE_EXPIRED'
                WHERE status = 'RUNNING' AND available_at <= ? AND attempts >= ?
                """, now, MAX_ATTEMPTS);
        UUID token = UUID.randomUUID();
        return jdbc.query("""
                SELECT id, repository_id, trigger_type, commit_sha, pr_number, attempts
                FROM revision_jobs
                WHERE status IN ('QUEUED', 'RUNNING') AND available_at <= ? AND attempts < ?
                ORDER BY available_at, id FETCH FIRST 1 ROW ONLY
                """, (row, index) -> {
            int pullRequest = row.getInt("pr_number");
            return new Lease(row.getObject("id", UUID.class), token, row.getInt("attempts") + 1,
                    new SourceChangeRequest(row.getObject("repository_id", UUID.class),
                            SourceChange.Trigger.valueOf(row.getString("trigger_type")), row.getString("commit_sha"),
                            pullRequest == 0 ? null : pullRequest));
        }, now, MAX_ATTEMPTS).stream().findFirst().filter(lease -> jdbc.update("""
                UPDATE revision_jobs SET status = 'RUNNING', available_at = ?, lease_token = ?, attempts = ?
                WHERE id = ? AND status IN ('QUEUED', 'RUNNING') AND available_at <= ? AND attempts = ?
                """, now.plus(LEASE_DURATION), lease.token(), lease.attempt(), lease.id(), now,
                lease.attempt() - 1) == 1);
    }

    public boolean lockCurrentLease(Lease lease, OffsetDateTime now) {
        return !jdbc.queryForList("""
                SELECT id FROM revision_jobs
                WHERE id = ? AND lease_token = ? AND status = 'RUNNING' AND available_at > ?
                FOR UPDATE
                """, UUID.class, lease.id(), lease.token(), now).isEmpty();
    }

    public void finish(Lease lease, OffsetDateTime now, String errorCode, boolean retryable) {
        String status = "COMPLETED";
        if (errorCode != null) {
            status = retryable && lease.attempt() < MAX_ATTEMPTS ? "QUEUED" : "FAILED";
        }
        OffsetDateTime nextAttempt = status.equals("QUEUED") ? now.plusSeconds(15L * lease.attempt()) : now;
        jdbc.update("""
                UPDATE revision_jobs SET status = ?, available_at = ?, error_code = ?, lease_token = NULL
                WHERE id = ? AND lease_token = ? AND status = 'RUNNING' AND available_at > ?
                """, status, nextAttempt, errorCode, lease.id(), lease.token(), now);
    }

    public record Lease(UUID id, UUID token, int attempt, SourceChangeRequest request) {
    }
}
