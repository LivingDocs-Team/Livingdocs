package com.livingdocs.github.service;

import com.livingdocs.github.exception.ApiException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * A Manager records that another Manager covers their approvals for a period. The record is shown to both
 * Managers and can be revoked. While a delegation is active the delegator is away: they cannot make final
 * decisions until it ends or is revoked, and the delegate's decisions are recorded as covering for them. The
 * approval queue itself stays shared by all Managers.
 */
@Service
public class ApprovalDelegationService {
    static final Duration MAX_PERIOD = Duration.ofDays(90);
    static final int MAX_ACTIVE = 10;

    public record Delegation(UUID id, String delegatorUserId, String delegateUserId, String reason,
                             Instant startsAt, Instant endsAt, Instant revokedAt, Instant createdAt, String state) { }

    public record Delegations(List<Delegation> outgoing, List<Delegation> incoming) { }

    public record CreateRequest(String delegateUserId, String reason, Instant startsAt, Instant endsAt) { }

    private final JdbcTemplate jdbc;

    public ApprovalDelegationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private static RowMapper<Delegation> mapper(Instant now) {
        return (rs, i) -> {
            Instant starts = rs.getTimestamp("starts_at").toInstant();
            Instant ends = rs.getTimestamp("ends_at").toInstant();
            Timestamp revoked = rs.getTimestamp("revoked_at");
            String state = revoked != null ? "REVOKED" : now.isBefore(starts) ? "SCHEDULED" : now.isBefore(ends) ? "ACTIVE" : "ENDED";
            return new Delegation(UUID.fromString(rs.getString("id")), rs.getString("delegator_user_id"),
                    rs.getString("delegate_user_id"), rs.getString("reason"), starts, ends,
                    revoked == null ? null : revoked.toInstant(), rs.getTimestamp("created_at").toInstant(), state);
        };
    }

    @Transactional(readOnly = true)
    public Delegations list(String actor) {
        Instant now = Instant.now();
        String columns = "SELECT id, delegator_user_id, delegate_user_id, reason, starts_at, ends_at, revoked_at, created_at"
                + " FROM approval_delegations ";
        return new Delegations(
                jdbc.query(columns + "WHERE delegator_user_id = ? ORDER BY created_at DESC LIMIT 50", mapper(now), actor),
                jdbc.query(columns + "WHERE delegate_user_id = ? ORDER BY created_at DESC LIMIT 50", mapper(now), actor));
    }

    /** The delegation under which the Manager is currently away, or null. */
    @Transactional(readOnly = true)
    public Delegation activeOutgoing(String actor) {
        Instant now = Instant.now();
        List<Delegation> found = jdbc.query("SELECT id, delegator_user_id, delegate_user_id, reason, starts_at, ends_at,"
                + " revoked_at, created_at FROM approval_delegations WHERE delegator_user_id = ? AND revoked_at IS NULL"
                + " AND starts_at <= ? AND ends_at > ? ORDER BY ends_at DESC LIMIT 1", mapper(now), actor,
                Timestamp.from(now), Timestamp.from(now));
        return found.isEmpty() ? null : found.get(0);
    }

    /** The Managers whose approvals this Manager currently covers. */
    @Transactional(readOnly = true)
    public List<String> covering(String actor) {
        Instant now = Instant.now();
        return jdbc.queryForList("SELECT DISTINCT delegator_user_id FROM approval_delegations WHERE delegate_user_id = ?"
                + " AND revoked_at IS NULL AND starts_at <= ? AND ends_at > ? ORDER BY delegator_user_id", String.class,
                actor, Timestamp.from(now), Timestamp.from(now));
    }

    /**
     * @param verifiedDelegate the Manager id the Backend confirmed (an active Manager who can approve); a request
     *        that does not carry it, or names someone else, is refused.
     */
    @Transactional
    public Delegation create(String actor, CreateRequest request, String verifiedDelegate) {
        if (request == null || request.delegateUserId() == null || request.delegateUserId().isBlank()) {
            throw ApiException.badRequest("Choose the Manager who covers your approvals.");
        }
        String delegate = request.delegateUserId().trim();
        if (verifiedDelegate == null || !verifiedDelegate.equals(delegate)) {
            throw ApiException.badRequest("The delegate must be an active Manager.");
        }
        if (activeOutgoing(delegate) != null) {
            throw new ApiException(org.springframework.http.HttpStatus.CONFLICT, "DELEGATE_UNAVAILABLE",
                    "That Manager has delegated their own approvals and cannot cover yours.");
        }
        if (delegate.length() > 100 || delegate.equals(actor)) {
            throw ApiException.badRequest("Choose a different Manager than yourself.");
        }
        Instant now = Instant.now().truncatedTo(java.time.temporal.ChronoUnit.MILLIS);
        Instant starts = request.startsAt() == null ? now : request.startsAt();
        Instant ends = request.endsAt();
        if (ends == null || !ends.isAfter(starts) || !ends.isAfter(now)) {
            throw ApiException.badRequest("The delegation must end in the future, after it starts.");
        }
        if (Duration.between(starts, ends).compareTo(MAX_PERIOD) > 0) {
            throw ApiException.badRequest("A delegation can last at most 90 days.");
        }
        String reason = request.reason() == null ? null : request.reason().trim();
        if (reason != null && reason.length() > 500) throw ApiException.badRequest("The reason can have at most 500 characters.");
        Long active = jdbc.queryForObject("SELECT COUNT(*) FROM approval_delegations WHERE delegator_user_id = ?"
                + " AND revoked_at IS NULL AND ends_at > ?", Long.class, actor, Timestamp.from(now));
        if (active != null && active >= MAX_ACTIVE) {
            throw new ApiException(org.springframework.http.HttpStatus.CONFLICT, "DELEGATION_LIMIT",
                    "Revoke a delegation before adding another one.");
        }
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO approval_delegations (id, delegator_user_id, delegate_user_id, reason, starts_at, ends_at, created_at)"
                        + " VALUES (?, ?, ?, ?, ?, ?, ?)", id, actor, delegate, reason == null || reason.isEmpty() ? null : reason,
                Timestamp.from(starts), Timestamp.from(ends), Timestamp.from(now));
        return jdbc.query("SELECT id, delegator_user_id, delegate_user_id, reason, starts_at, ends_at, revoked_at, created_at"
                + " FROM approval_delegations WHERE id = ?", mapper(now), id).get(0);
    }

    @Transactional
    public void revoke(String actor, UUID id) {
        int updated = jdbc.update("UPDATE approval_delegations SET revoked_at = ? WHERE id = ? AND delegator_user_id = ?"
                + " AND revoked_at IS NULL", Timestamp.from(Instant.now()), id, actor);
        if (updated == 0) throw ApiException.notFound("Delegation not found.");
    }
}
