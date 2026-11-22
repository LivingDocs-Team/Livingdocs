package com.livingdocs.github.change;

import com.livingdocs.github.entity.SourceChange;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.service.RepositoryManagementService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.UUID;

@Service
public class AutoUpdatePolicies {
    private final JdbcTemplate jdbc;
    private final ConnectedRepositoryRepository repositories;
    private final RepositoryManagementService access;

    public AutoUpdatePolicies(JdbcTemplate jdbc, ConnectedRepositoryRepository repositories,
            RepositoryManagementService access) {
        this.jdbc = jdbc;
        this.repositories = repositories;
        this.access = access;
    }

    @Transactional(readOnly = true)
    public List<Rule> get(String actor, String workspace, UUID repository) {
        access.get(actor, repository, workspace, "OWNER");
        return rules(repository);
    }

    @Transactional
    public List<Rule> replace(String actor, String workspace, UUID repository, List<Rule> rules) {
        repositories.lockById(repository).orElseThrow(() -> ApiException.notFound("Repository not found."));
        access.get(actor, repository, workspace, "OWNER");
        if (rules == null || rules.size() > 100) {
            throw ApiException.badRequest("Supply up to 100 auto-update policies.");
        }
        var keys = new HashSet<RuleKey>();
        for (Rule rule : rules) {
            if (rule == null || !rule.valid() || !keys.add(new RuleKey(rule.scope(), rule.target()))) {
                throw ApiException.badRequest("Each policy needs a unique valid scope and target and both triggers.");
            }
        }
        jdbc.update("DELETE FROM auto_update_policies WHERE repository_id = ?", repository);
        for (Rule rule : rules) {
            jdbc.update("""
                    INSERT INTO auto_update_policies (repository_id, scope, target, on_commit, on_pull_request)
                    VALUES (?, ?, ?, ?, ?)
                    """, repository, rule.scope().name(), rule.target(), rule.onCommit(), rule.onPullRequest());
        }
        return rules(repository);
    }

    boolean allows(UUID repository, SourceChange.Trigger trigger, String documentId,
            String documentScope, String documentTarget) {
        return rules(repository).stream()
                .filter(rule -> rule.matches(documentId, documentScope, documentTarget))
                .max(Comparator.<Rule>comparingInt(rule -> rule.scope().ordinal())
                        .thenComparingInt(rule -> rule.target().length()))
                .map(rule -> trigger == SourceChange.Trigger.COMMIT ? rule.onCommit() : rule.onPullRequest())
                .orElse(true);
    }

    private List<Rule> rules(UUID repository) {
        return jdbc.query("""
                SELECT scope, target, on_commit, on_pull_request FROM auto_update_policies
                WHERE repository_id = ? ORDER BY scope, target
                """, (row, index) -> new Rule(Scope.valueOf(row.getString("scope")), row.getString("target"),
                row.getBoolean("on_commit"), row.getBoolean("on_pull_request")), repository);
    }

    public enum Scope { REPOSITORY, MODULE, DOCUMENT }

    private record RuleKey(Scope scope, String target) { }

    public record Rule(Scope scope, String target, Boolean onCommit, Boolean onPullRequest) {
        private boolean valid() {
            if (scope == null || target == null || target.length() > 500 || onCommit == null || onPullRequest == null) {
                return false;
            }
            return switch (scope) {
                case REPOSITORY -> target.isEmpty();
                case DOCUMENT -> target.matches("[0-9a-f]{32}");
                case MODULE -> !target.contains("\\") && !target.chars().anyMatch(Character::isISOControl)
                        && Arrays.stream(target.split("/", -1))
                                .noneMatch(part -> part.isBlank() || part.equals(".") || part.equals(".."));
            };
        }

        private boolean matches(String documentId, String documentScope, String documentTarget) {
            return switch (scope) {
                case REPOSITORY -> true;
                case DOCUMENT -> target.equals(documentId);
                case MODULE -> ("module".equals(documentScope) && target.equals(documentTarget))
                        || (("module".equals(documentScope) || "file".equals(documentScope))
                                && documentTarget.startsWith(target + "/"));
            };
        }
    }
}
