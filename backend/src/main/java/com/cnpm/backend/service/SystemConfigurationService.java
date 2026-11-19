package com.cnpm.backend.service;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.function.Function;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import com.cnpm.backend.entity.SystemSetting;
import com.cnpm.backend.repository.SystemSettingRepository;

/**
 * LD-273: System configuration for LivingDocs.
 *
 * Every setting is declared once in the catalog below with its type, default and validation. The
 * defaults mirror the values the services use today (github-integration-service application.yml,
 * SyncOptions, LanguageDetector, ai-service generator / retrieval / confidence), so a fresh system
 * behaves exactly as before. Only administrator overrides are stored (table system_settings).
 *
 * Secrets (GitHub client secret, webhook secret, token-encryption key, API keys) are NOT settings:
 * they stay in environment variables and the API rejects any key that is not in the catalog.
 */
@Service
public class SystemConfigurationService {
    private static final Logger log = LoggerFactory.getLogger(SystemConfigurationService.class);

    public enum Type { STRING, INT, DECIMAL, BOOLEAN, CHOICE, LIST }

    /** One configurable setting. {@code allowed} is used by CHOICE/LIST, {@code pattern} by STRING and free-form LIST items. */
    public record Definition(String group, String key, Type type, String defaultValue, String description,
                             BigDecimal min, BigDecimal max, List<String> allowed, Pattern pattern, int minItems) { }

    public record SettingView(String key, String type, Object value, Object defaultValue, String description,
                              BigDecimal min, BigDecimal max, List<String> allowedValues,
                              boolean overridden, Instant updatedAt, String updatedBy) { }

    public record GroupView(String id, String title, List<SettingView> settings) { }

    private static final int MAX_TEXT_LENGTH = 255;
    private static final int MAX_LIST_ITEMS = 20;
    private static final String URL = "^https?://[^\\s,]+$";
    private static final String OPTIONAL_URL = "^(https?://[^\\s,]+)?$";
    private static final List<String> LANGUAGES = List.of("java", "python", "javascript", "typescript", "kotlin",
            "go", "ruby", "php", "csharp", "c", "cpp", "rust", "swift", "scala", "sql");

    private static final Map<String, String> GROUPS = new LinkedHashMap<>();
    private static final Map<String, Definition> CATALOG = new LinkedHashMap<>();

    static {
        // LD-274 - GitHub App & OAuth (public identifiers only; secrets stay in the environment)
        group("github", "GitHub App & OAuth");
        text("github", "github.appSlug", "livingdocs-dev-hai", "GitHub App slug used in the installation URL.",
                "^[A-Za-z0-9][A-Za-z0-9-]{0,99}$");
        text("github", "github.clientId", "", "OAuth client ID of the GitHub App (public identifier, not the secret).",
                "^[A-Za-z0-9._-]{0,100}$");
        text("github", "github.redirectUri", "http://localhost:8082/api/github/callback",
                "OAuth redirect URI; must match the one registered on GitHub.", URL);
        list("github", "github.oauthScopes", "read:user,user:email", null, "^[a-z][a-z:_]{0,49}$", 1,
                "OAuth scopes requested at login.");
        text("github", "github.oauthBaseUrl", "https://github.com", "GitHub OAuth base URL.", URL);
        text("github", "github.apiBaseUrl", "https://api.github.com", "GitHub REST API base URL.", URL);

        // LD-275 - GitHub Actions & webhooks
        group("actions-webhooks", "GitHub Actions & Webhooks");
        text("actions-webhooks", "actions.workflowFile", ".github/workflows/ci.yml",
                "CI workflow file of the repository.", "^\\.github/workflows/[A-Za-z0-9._-]+\\.ya?ml$");
        list("actions-webhooks", "actions.requiredChecks",
                "Backend Build and Test,Frontend Build and Test,GitHub Integration Service Test,AI Service Build and Test",
                null, "^[A-Za-z0-9][A-Za-z0-9 ._()/-]{0,99}$", 0, "CI jobs that must pass before a change is accepted.");
        flag("actions-webhooks", "webhooks.enabled", true, "Accept GitHub webhook deliveries.");
        list("actions-webhooks", "webhooks.events", "push,pull_request", List.of("push", "pull_request"), null, 1,
                "GitHub events the webhook receiver processes (others are ignored).");
        text("actions-webhooks", "webhooks.payloadUrl", "",
                "Public URL of POST /api/github/webhook as registered on the GitHub App (empty = not set).", OPTIONAL_URL);

        // Supported source-code languages
        group("languages", "Supported Source-Code Languages");
        list("languages", "languages.enabled", "java,python", LANGUAGES, null, 1,
                "Languages whose files are synchronised and analysed (the code analyzer currently parses java and python).");

        // LD-277 - Documentation generation
        group("generation", "Documentation Generation");
        choice("generation", "generation.outputLanguage", "vi", List.of("vi", "en"), "Language of generated documentation.");
        text("generation", "generation.templateId", "default", "Template used when none is chosen.",
                "^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$");
        list("generation", "generation.sections", "Overview,Classes,Functions,API Endpoints",
                List.of("Overview", "Classes", "Functions", "API Endpoints"), null, 1, "Sections included in generated documentation.");
        integer("generation", "generation.maxAttempts",
            envInt("GENERATION_MAX_ATTEMPTS", 3), 1, 10,
            "AI attempts per file before falling back to analysis data only.");

        // LD-278 - Automatic documentation update triggers and policies
        group("auto-update", "Automatic Update Policies");
        flag("auto-update", "autoUpdate.enabled", false, "Update documentation automatically when the code changes.");
        list("auto-update", "autoUpdate.triggers", "push,pull_request", List.of("push", "pull_request"), null, 1,
                "GitHub events that start an automatic documentation update.");
        list("auto-update", "autoUpdate.branches", "main", null, "^[A-Za-z0-9._/*-]{1,100}$", 1,
                "Branches (a trailing * is a wildcard) that trigger updates.");
        choice("auto-update", "autoUpdate.minDriftSeverity", "medium", List.of("low", "medium", "high", "critical"),
                "Lowest documentation-drift severity that triggers an update.");
        flag("auto-update", "autoUpdate.requireReview", true, "Updated documentation still goes through staff review and manager approval.");

        // Change-log and audit-log retention
        group("retention", "Change-Log & Audit-Log Retention");
                integer("retention", "retention.changeLogDays",
                envInt("RETENTION_CHANGE_LOG_DAYS", 365), 30, 3650,
                "Days to keep change-log entries.");
        integer("retention", "retention.auditLogDays",
                envInt("ADMIN_USER_AUDIT_RETENTION_DAYS", 730), 30, 3650,
                "Days to keep audit-log entries.");

        // LD-279 - AI model, embedding model, confidence threshold, token budget
        group("ai", "AI Model & Confidence");
        text("ai", "ai.model", "claude-sonnet-5-5", "Model that writes the documentation.", "^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$");
        text("ai", "ai.embeddingModel", "tfidf", "Embedding model for retrieval (tfidf = the built-in TF-IDF ranking).",
                "^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$");
        decimal("ai", "ai.confidenceThreshold", "0.5", "0", "1", "Entities scoring below this confidence are flagged for review.");
        integer("ai", "ai.tokenBudget", 4096, 256, 64000, "Maximum tokens of one AI response.");

        // LD-279 - Documentation indexing and retrieval
        group("retrieval", "Indexing & Retrieval");
        flag("retrieval", "indexing.reindexOnChange", true, "Rebuild the documentation index when code or documents change.");
        integer("retrieval", "retrieval.codeResults", 4, 0, 20, "Related code items given to the AI per file.");
        integer("retrieval", "retrieval.docResults", 3, 0, 20, "Documentation passages given to the AI per file.");
        decimal("retrieval", "retrieval.minScore", "0.05", "0", "1", "Minimum similarity for a retrieved item.");
        integer("retrieval", "retrieval.chunkChars", 1200, 200, 10000, "Maximum characters of one indexed documentation passage.");
        integer("retrieval", "retrieval.excerptChars", 600, 100, 5000, "Maximum characters of an excerpt shown as evidence.");

        // Fail fast if a default does not satisfy its own validation.
        CATALOG.values().forEach(d -> coerce(d, d.defaultValue()));
    }

    private final SystemSettingRepository repository;

    public SystemConfigurationService(SystemSettingRepository repository) {
        this.repository = repository;
    }

    // ---------------------------------------------------------------- queries

    @Transactional(readOnly = true)
    public List<GroupView> getAll() {
        Map<String, SystemSetting> stored = repository.findAll().stream()
                .collect(Collectors.toMap(SystemSetting::getKey, Function.identity(), (a, b) -> a));
        return GROUPS.keySet().stream().map(id -> view(id, stored)).toList();
    }

    @Transactional(readOnly = true)
    public GroupView getGroup(String groupId) {
        String id = requireGroup(groupId);
        return view(id, storedFor(id));
    }

    /** Typed accessors for code that consumes a setting. */
    @Transactional(readOnly = true)
    public Object get(String key) {
        Definition d = CATALOG.get(key);
        if (d == null) throw new IllegalArgumentException("Unknown setting: " + key);
        Optional<SystemSetting> row = repository.findById(key);
        return row.isPresent() ? decodeOrDefault(d, row.get().getValue()) : coerce(d, d.defaultValue());
    }

    public String getString(String key) { return (String) get(key); }
    public int getInt(String key) { return (Integer) get(key); }
    public boolean getBoolean(String key) { return (Boolean) get(key); }
    public BigDecimal getDecimal(String key) { return (BigDecimal) get(key); }

    @SuppressWarnings("unchecked")
    public List<String> getList(String key) { return (List<String>) get(key); }

    public boolean isAutoUpdateEnabled()       { return getBoolean("autoUpdate.enabled"); }
    public int     getGenerationMaxAttempts()  { return getInt("generation.maxAttempts"); }
    public int     getAuditLogRetentionDays()  { return getInt("retention.auditLogDays"); }
    public int     getChangeLogRetentionDays() { return getInt("retention.changeLogDays"); }


    /** Validates every value first, then stores them all (a single invalid value changes nothing). */
    @Transactional
    public GroupView update(String groupId, Map<String, Object> changes, String actor) {
        String id = requireGroup(groupId);
        if (changes == null || changes.isEmpty()) throw bad("settings must contain at least one value");

        Map<String, Object> valid = new LinkedHashMap<>();
        List<String> errors = new ArrayList<>();
        changes.forEach((key, raw) -> {
            Definition d = CATALOG.get(key);
            if (d == null || !d.group().equals(id)) {
                errors.add(key + " is not a setting of group '" + id + "'");
                return;
            }
            try {
                valid.put(key, coerce(d, raw));
            } catch (IllegalArgumentException e) {
                errors.add(key + " " + e.getMessage());
            }
        });
        if (!errors.isEmpty()) throw bad("Invalid settings: " + String.join("; ", errors));

        valid.forEach((key, value) -> {
            SystemSetting row = repository.findById(key).orElseGet(() -> new SystemSetting(key));
            row.update(encode(CATALOG.get(key), value), actor);
            repository.save(row);
        });
        log.info("System configuration group '{}' updated by {}: {}", id, actor, valid.keySet());
        return view(id, storedFor(id));
    }

    /** Removes the overrides of a group so every setting returns to its default. */
    @Transactional
    public GroupView reset(String groupId) {
        String id = requireGroup(groupId);
        repository.deleteAllById(keysOf(id));
        log.info("System configuration group '{}' reset to defaults", id);
        return view(id, Map.of());
    }

    // ---------------------------------------------------------------- views

    private Map<String, SystemSetting> storedFor(String groupId) {
        return repository.findAllById(keysOf(groupId)).stream()
                .collect(Collectors.toMap(SystemSetting::getKey, Function.identity(), (a, b) -> a));
    }

    private static List<String> keysOf(String groupId) {
        return CATALOG.values().stream().filter(d -> d.group().equals(groupId)).map(Definition::key).toList();
    }

    private static GroupView view(String groupId, Map<String, SystemSetting> stored) {
        List<SettingView> settings = CATALOG.values().stream()
                .filter(d -> d.group().equals(groupId))
                .map(d -> {
                    SystemSetting row = stored.get(d.key());
                    Object fallback = coerce(d, d.defaultValue());
                    Object value = row == null ? fallback : decodeOrDefault(d, row.getValue());
                    return new SettingView(d.key(), d.type().name(), value, fallback, d.description(), d.min(), d.max(),
                            d.allowed(), row != null, row == null ? null : row.getUpdatedAt(),
                            row == null ? null : row.getUpdatedBy());
                }).toList();
        return new GroupView(groupId, GROUPS.get(groupId), settings);
    }

    private static String requireGroup(String groupId) {
        String id = groupId == null ? "" : groupId.trim().toLowerCase(Locale.ROOT);
        if (!GROUPS.containsKey(id)) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Configuration group not found");
        return id;
    }

    private static ResponseStatusException bad(String message) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, message);
    }

    // ---------------------------------------------------------------- validation / storage format

    private static Object decodeOrDefault(Definition d, String stored) {
        try {
            return coerce(d, stored);
        } catch (IllegalArgumentException e) {
            log.warn("Stored value of {} is invalid ({}); using the default", d.key(), e.getMessage());
            return coerce(d, d.defaultValue());
        }
    }

    private static String encode(Definition d, Object value) {
        if (value instanceof List<?> items) return items.stream().map(String::valueOf).collect(Collectors.joining(","));
        if (value instanceof BigDecimal n) return n.toPlainString();
        return String.valueOf(value);
    }

    /** Converts a JSON / stored value to the setting's type, or throws IllegalArgumentException (message = reason). */
    private static Object coerce(Definition d, Object raw) {
        if (raw == null) throw new IllegalArgumentException("needs a value (use reset to restore the default)");
        return switch (d.type()) {
            case STRING -> asText(d, raw);
            case INT -> asInt(d, raw);
            case DECIMAL -> asDecimal(d, raw);
            case BOOLEAN -> asBoolean(raw);
            case CHOICE -> asChoice(d, raw);
            case LIST -> asList(d, raw);
        };
    }

    private static String asText(Definition d, Object raw) {
        if (!(raw instanceof String s)) throw new IllegalArgumentException("must be a string");
        String value = s.trim();
        if (value.length() > MAX_TEXT_LENGTH) throw new IllegalArgumentException("must be at most " + MAX_TEXT_LENGTH + " characters");
        if (d.pattern() != null && !d.pattern().matcher(value).matches()) throw new IllegalArgumentException("has an invalid format");
        return value;
    }

    private static Integer asInt(Definition d, Object raw) {
        BigDecimal n = asNumber(raw);
        if (n.stripTrailingZeros().scale() > 0) throw new IllegalArgumentException("must be a whole number");
        checkRange(d, n);
        return n.intValueExact();
    }

    private static BigDecimal asDecimal(Definition d, Object raw) {
        BigDecimal n = asNumber(raw);
        checkRange(d, n);
        return n.signum() == 0 ? BigDecimal.ZERO : n.stripTrailingZeros();
    }

    private static BigDecimal asNumber(Object raw) {
        try {
            if (raw instanceof Number || raw instanceof String) return new BigDecimal(raw.toString().trim());
        } catch (NumberFormatException e) {
            // handled below
        }
        throw new IllegalArgumentException("must be a number");
    }

    private static void checkRange(Definition d, BigDecimal n) {
        if (n.compareTo(d.min()) < 0 || n.compareTo(d.max()) > 0) {
            throw new IllegalArgumentException("must be between " + d.min().toPlainString() + " and " + d.max().toPlainString());
        }
    }

    private static Boolean asBoolean(Object raw) {
        if (raw instanceof Boolean b) return b;
        if (raw instanceof String s && (s.trim().equalsIgnoreCase("true") || s.trim().equalsIgnoreCase("false"))) {
            return Boolean.parseBoolean(s.trim());
        }
        throw new IllegalArgumentException("must be true or false");
    }

    private static String asChoice(Definition d, Object raw) {
        if (!(raw instanceof String s)) throw new IllegalArgumentException("must be a string");
        return canonical(d, s.trim());
    }

    private static String canonical(Definition d, String value) {
        return d.allowed().stream().filter(a -> a.equalsIgnoreCase(value)).findFirst()
                .orElseThrow(() -> new IllegalArgumentException("must be one of " + d.allowed()));
    }

    private static List<String> asList(Definition d, Object raw) {
        List<String> parts = new ArrayList<>();
        if (raw instanceof Collection<?> items) {
            for (Object item : items) {
                if (!(item instanceof String s)) throw new IllegalArgumentException("must contain only strings");
                parts.add(s);
            }
        } else if (raw instanceof String s) {
            parts.addAll(Arrays.asList(s.split(",")));
        } else {
            throw new IllegalArgumentException("must be a list of strings");
        }
        LinkedHashSet<String> result = new LinkedHashSet<>();
        for (String part : parts) {
            String value = part.trim();
            if (value.isEmpty()) continue;
            if (d.allowed() != null) {
                value = canonical(d, value);
            } else if (!d.pattern().matcher(value).matches()) {
                throw new IllegalArgumentException("contains an invalid item '" + value + "'");
            }
            result.add(value);
        }
        if (result.size() < d.minItems()) throw new IllegalArgumentException("must contain at least " + d.minItems() + " item(s)");
        if (result.size() > MAX_LIST_ITEMS) throw new IllegalArgumentException("must contain at most " + MAX_LIST_ITEMS + " items");
        return List.copyOf(result);
    }

        // ---------------------------------------------------------------- env fallback (LD-273)

    /**
     * Reads an integer from an environment variable, falling back to {@code defaultValue} when the
     * variable is unset, blank or not a number. Deployments keep configuring the same values through
     * environment variables, but the database override (system_settings) remains the top priority.
     */
    private static int envInt(String name, int defaultValue) {
        String raw = System.getenv(name);
        if (raw == null || raw.isBlank()) return defaultValue;
        try {
            return Integer.parseInt(raw.trim());
        } catch (NumberFormatException e) {
            log.warn("Environment variable {}={} is not an integer; using default {}", name, raw, defaultValue);
            return defaultValue;
        }
    }

    // ---------------------------------------------------------------- catalog builders

    // ---------------------------------------------------------------- catalog builders

    private static void group(String id, String title) {
        GROUPS.put(id, title);
    }

    private static void add(Definition d) {
        CATALOG.put(d.key(), d);
    }

    private static void text(String group, String key, String def, String description, String regex) {
        add(new Definition(group, key, Type.STRING, def, description, null, null, null, Pattern.compile(regex), 0));
    }

    private static void integer(String group, String key, int def, int min, int max, String description) {
        add(new Definition(group, key, Type.INT, String.valueOf(def), description,
                BigDecimal.valueOf(min), BigDecimal.valueOf(max), null, null, 0));
    }

    private static void decimal(String group, String key, String def, String min, String max, String description) {
        add(new Definition(group, key, Type.DECIMAL, def, description, new BigDecimal(min), new BigDecimal(max), null, null, 0));
    }

    private static void flag(String group, String key, boolean def, String description) {
        add(new Definition(group, key, Type.BOOLEAN, String.valueOf(def), description, null, null, null, null, 0));
    }

    private static void choice(String group, String key, String def, List<String> allowed, String description) {
        add(new Definition(group, key, Type.CHOICE, def, description, null, null, allowed, null, 0));
    }

    private static void list(String group, String key, String def, List<String> allowed, String itemRegex,
                             int minItems, String description) {
        add(new Definition(group, key, Type.LIST, def, description, null, null, allowed,
                itemRegex == null ? null : Pattern.compile(itemRegex), minItems));
    }
}

