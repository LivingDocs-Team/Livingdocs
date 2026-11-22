package com.livingdocs.github.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.exception.ApiException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * The approval policy (what a review or an approval must contain) and the merge policy (how an approved
 * document is published to GitHub). One row per policy type; a type without a row uses the defaults, which keep
 * the behaviour the service had before policies existed.
 */
@Service
public class ApprovalPolicyService {
    public static final String APPROVAL = "APPROVAL";
    public static final String MERGE = "MERGE";
    private static final int TEMPLATE_MAX = 200;
    private static final Set<String> TEMPLATE_FIELDS = Set.of("{document}", "{version}");

    public record ApprovalSettings(boolean requireStaffComment, boolean requireManagerComment) {
        static ApprovalSettings defaults() { return new ApprovalSettings(false, false); }
    }

    public record MergeSettings(boolean allowCommitBack, String commitMessageTemplate) {
        static final String DEFAULT_TEMPLATE = "Publish LivingDocs document {document} v{version}";
        static MergeSettings defaults() { return new MergeSettings(true, DEFAULT_TEMPLATE); }

        /** The commit message for one document version. */
        public String message(String documentId, int version) {
            return commitMessageTemplate.replace("{document}", documentId).replace("{version}", String.valueOf(version));
        }
    }

    public record PolicyView(String type, Object settings, String updatedBy, Instant updatedAt) { }

    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public ApprovalPolicyService(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @Transactional(readOnly = true)
    public ApprovalSettings approval() {
        return read(APPROVAL, ApprovalSettings.class, ApprovalSettings.defaults());
    }

    @Transactional(readOnly = true)
    public MergeSettings merge() {
        return read(MERGE, MergeSettings.class, MergeSettings.defaults());
    }

    @Transactional(readOnly = true)
    public PolicyView view(String rawType) {
        String type = type(rawType);
        Object settings = APPROVAL.equals(type) ? approval() : merge();
        List<PolicyView> rows = jdbc.query("SELECT updated_by, updated_at FROM approval_policies WHERE policy_type = ?",
                (rs, i) -> new PolicyView(type, settings, rs.getString("updated_by"),
                        rs.getTimestamp("updated_at").toInstant()), type);
        return rows.isEmpty() ? new PolicyView(type, settings, null, null) : rows.get(0);
    }

    @Transactional
    public PolicyView replace(String actor, String rawType, com.fasterxml.jackson.databind.JsonNode body) {
        String type = type(rawType);
        Object settings;
        if (APPROVAL.equals(type)) {
            settings = new ApprovalSettings(flag(body, "requireStaffComment"), flag(body, "requireManagerComment"));
        } else {
            String template = body == null || !body.hasNonNull("commitMessageTemplate")
                    ? MergeSettings.DEFAULT_TEMPLATE : body.get("commitMessageTemplate").asText().trim();
            validateTemplate(template);
            settings = new MergeSettings(flag(body, "allowCommitBack"), template);
        }
        String json;
        try {
            json = mapper.writeValueAsString(settings);
        } catch (JsonProcessingException e) {
            throw ApiException.badRequest("The policy could not be saved.");
        }
        Instant now = Instant.now();
        int updated = jdbc.update("UPDATE approval_policies SET settings = ?, updated_by = ?, updated_at = ? WHERE policy_type = ?",
                json, actor, java.sql.Timestamp.from(now), type);
        if (updated == 0) {
            jdbc.update("INSERT INTO approval_policies (policy_type, settings, updated_by, updated_at) VALUES (?, ?, ?, ?)",
                    type, json, actor, java.sql.Timestamp.from(now));
        }
        return new PolicyView(type, settings, actor, now);
    }

    private static boolean flag(com.fasterxml.jackson.databind.JsonNode body, String name) {
        if (body == null || !body.has(name)) return false;
        if (!body.get(name).isBoolean()) throw ApiException.badRequest(name + " must be true or false.");
        return body.get(name).asBoolean();
    }

    private static void validateTemplate(String template) {
        if (template.isBlank() || template.length() > TEMPLATE_MAX || template.contains("\n") || template.contains("\r")) {
            throw ApiException.badRequest("The commit message must be one line of 1 to " + TEMPLATE_MAX + " characters.");
        }
        var open = java.util.regex.Pattern.compile("\\{[^}]*}").matcher(template);
        while (open.find()) {
            if (!TEMPLATE_FIELDS.contains(open.group())) {
                throw ApiException.badRequest("Unknown field " + open.group() + ". Use {document} and {version}.");
            }
        }
    }

    private static String type(String raw) {
        String type = raw == null ? "" : raw.toUpperCase(Locale.ROOT);
        if (!APPROVAL.equals(type) && !MERGE.equals(type)) throw ApiException.notFound("Unknown policy.");
        return type;
    }

    private <T> T read(String type, Class<T> kind, T fallback) {
        List<String> rows = jdbc.queryForList("SELECT settings FROM approval_policies WHERE policy_type = ?", String.class, type);
        if (rows.isEmpty()) return fallback;
        try {
            return mapper.readValue(rows.get(0), kind);
        } catch (JsonProcessingException e) {
            return fallback;
        }
    }
}
