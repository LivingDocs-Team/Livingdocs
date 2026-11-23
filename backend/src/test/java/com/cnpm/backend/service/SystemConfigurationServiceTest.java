package com.cnpm.backend;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentMatchers;
import org.springframework.http.HttpStatus;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.web.server.ResponseStatusException;

import com.cnpm.backend.controller.AdminSystemConfigController;
import com.cnpm.backend.controller.AdminSystemConfigController.UpdateSystemConfigRequest;
import com.cnpm.backend.entity.SystemSetting;
import com.cnpm.backend.repository.AdminUserAuditRepository;
import com.cnpm.backend.service.AdminUserAuditRetention;
import com.cnpm.backend.repository.SystemSettingRepository;
import com.cnpm.backend.service.SystemConfigurationService;
import com.cnpm.backend.service.SystemConfigurationService.GroupView;
import com.cnpm.backend.service.SystemConfigurationService.SettingView;

class SystemConfigurationServiceTest {
    private final Map<String, SystemSetting> rows = new HashMap<>();
    private final SystemSettingRepository repository = mock(SystemSettingRepository.class);
    private SystemConfigurationService service;

    @BeforeEach
    void setUp() {
        when(repository.findAll()).thenAnswer(call -> new ArrayList<>(rows.values()));
        when(repository.findAllById(ArgumentMatchers.<Iterable<String>>any())).thenAnswer(call -> {
            List<SystemSetting> found = new ArrayList<>();
            for (Object id : (Iterable<?>) call.getArgument(0)) {
                if (rows.containsKey(id)) found.add(rows.get(id));
            }
            return found;
        });
        when(repository.findById(anyString()))
                .thenAnswer(call -> Optional.ofNullable(rows.get(call.<String>getArgument(0))));
        when(repository.save(any(SystemSetting.class))).thenAnswer(call -> {
            SystemSetting row = call.getArgument(0);
            rows.put(row.getKey(), row);
            return row;
        });
        doAnswer(call -> {
            for (Object id : (Iterable<?>) call.getArgument(0)) rows.remove(id);
            return null;
        }).when(repository).deleteAllById(ArgumentMatchers.<Iterable<? extends String>>any());
        service = new SystemConfigurationService(repository);
    }


    @Test
    void auditDashboardAndSchedulerUseTheSamePersistedPolicy() {
        var dashboard = new AdminSystemConfigController(service, "http://localhost:3000", false,
                "Lax", new MockEnvironment(), "http://localhost:8082", "",
                Duration.ofSeconds(5), Duration.ofSeconds(150));
        var authentication = new TestingAuthenticationToken("admin", "unused");
        var audit = mock(AdminUserAuditRepository.class);
        var reloadedService = new SystemConfigurationService(repository);
        var scheduler = new AdminUserAuditRetention(audit, reloadedService);

        assertThat(dashboard.updateConfig(new UpdateSystemConfigRequest(BigDecimal.ZERO), authentication)
                .audit().retentionDays()).isZero();
        assertThat(rows.get("retention.auditLogDays").getUpdatedBy()).isEqualTo("admin");
        scheduler.purgeExpiredRecords();
        verify(audit, never()).deleteOlderThan(any());

        service.update("retention", Map.of("retention.auditLogDays", 30), "admin");
        assertThat(dashboard.getConfig().audit().retentionDays()).isEqualTo(30);
        scheduler.purgeExpiredRecords();
        verify(audit).deleteOlderThan(any());

        dashboard.updateConfig(new UpdateSystemConfigRequest(BigDecimal.valueOf(3650)), authentication);
        assertThat(reloadedService.getAuditLogRetentionDays()).isEqualTo(3650);
        for (String invalid : List.of("-1", "1", "29", "30.5", "3651")) {
            assertThatThrownBy(() -> dashboard.updateConfig(
                    new UpdateSystemConfigRequest(new BigDecimal(invalid)), authentication))
                    .isInstanceOf(ResponseStatusException.class);
            assertThat(reloadedService.getAuditLogRetentionDays()).isEqualTo(3650);
        }
    }

    @Test
    void invalidStoredAuditPolicyKeepsRecordsInsteadOfUsingThePurgeDefault() {
        var invalid = new SystemSetting("retention.auditLogDays");
        invalid.update("29", "admin");
        rows.put(invalid.getKey(), invalid);

        assertThat(service.getAuditLogRetentionDays()).isZero();
        assertThat(service.getGroup("retention").settings().get(0).value()).isEqualTo(0);
    }

    @Test
    void defaultsMirrorTheValuesTheServicesUseToday() {
        assertThat(service.getAll()).extracting(GroupView::id).containsExactly("github", "actions-webhooks",
                "languages", "generation", "auto-update", "retention", "ai", "retrieval");

        assertThat(service.getString("ai.model")).isEqualTo("claude-sonnet-5-5");
        assertThat(service.getInt("ai.tokenBudget")).isEqualTo(4096);
        assertThat(service.getDecimal("ai.confidenceThreshold")).isEqualByComparingTo("0.5");
        assertThat(service.getList("languages.enabled")).containsExactly("java", "python");
        assertThat(service.getList("github.oauthScopes")).containsExactly("read:user", "user:email");
        assertThat(service.getList("webhooks.events")).containsExactly("push", "pull_request");
        assertThat(service.getInt("retrieval.chunkChars")).isEqualTo(1200);
        assertThat(service.getBoolean("autoUpdate.enabled")).isFalse();
        assertThat(service.getBoolean("autoUpdate.requireReview")).isTrue();
        service.getAll().forEach(group -> group.settings().forEach(s -> assertThat(s.overridden()).isFalse()));
    }

    @Test
    void updateStoresValidatedValuesAndRecordsWhoChangedThem() {
        GroupView ai = service.update("ai", Map.of("ai.model", "claude-opus-5-5", "ai.confidenceThreshold", 0.7,
                "ai.tokenBudget", 8000), "admin");

        assertThat(service.getString("ai.model")).isEqualTo("claude-opus-5-5");
        assertThat(service.getDecimal("ai.confidenceThreshold")).isEqualByComparingTo(new BigDecimal("0.7"));
        assertThat(service.getInt("ai.tokenBudget")).isEqualTo(8000);
        SettingView model = ai.settings().stream().filter(s -> s.key().equals("ai.model")).findFirst().orElseThrow();
        assertThat(model.overridden()).isTrue();
        assertThat(model.updatedBy()).isEqualTo("admin");
        assertThat(model.defaultValue()).isEqualTo("claude-sonnet-5-5");
        SettingView embedding = ai.settings().stream().filter(s -> s.key().equals("ai.embeddingModel")).findFirst().orElseThrow();
        assertThat(embedding.overridden()).isFalse();
    }

    @Test
    void updateIsAllOrNothing() {
        assertThatThrownBy(() -> service.update("ai", Map.of("ai.model", "other-model", "ai.confidenceThreshold", 1.5), "admin"))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(error -> assertThat(((ResponseStatusException) error).getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST));

        verify(repository, never()).save(any(SystemSetting.class));
        assertThat(service.getString("ai.model")).isEqualTo("claude-sonnet-5-5");
    }

    @Test
    void rejectsUnknownKeysAndKeysOfAnotherGroup() {
        assertThatThrownBy(() -> service.update("ai", Map.of("ai.apiKey", "secret"), "admin"))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("ai.apiKey");
        assertThatThrownBy(() -> service.update("ai", Map.of("retention.auditLogDays", 90), "admin"))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("retention.auditLogDays");
        assertThatThrownBy(() -> service.update("ai", Map.of(), "admin"))
                .isInstanceOf(ResponseStatusException.class);
    }

    @Test
    void rejectsValuesOfTheWrongTypeOrOutsideTheAllowedRange() {
        assertInvalid("ai", "ai.confidenceThreshold", 1.5);
        assertInvalid("ai", "ai.tokenBudget", 10);
        assertInvalid("ai", "ai.tokenBudget", 4096.5);
        assertInvalid("retention", "retention.auditLogDays", "abc");
        assertInvalid("retention", "retention.changeLogDays", 7);
        assertInvalid("actions-webhooks", "webhooks.enabled", "maybe");
        assertInvalid("actions-webhooks", "webhooks.events", List.of("issues"));
        assertInvalid("actions-webhooks", "webhooks.payloadUrl", "ftp://example.com/hook");
        assertInvalid("github", "github.redirectUri", "not a url");
        assertInvalid("languages", "languages.enabled", List.of("cobol"));
        assertInvalid("languages", "languages.enabled", List.of());
        assertInvalid("generation", "generation.outputLanguage", "fr");
        assertInvalid("generation", "generation.maxAttempts", 0);
        assertInvalid("auto-update", "autoUpdate.minDriftSeverity", "urgent");
        assertInvalid("retrieval", "retrieval.minScore", -0.1);
        assertInvalid("ai", "ai.model", null);
    }

    @Test
    void listsAndChoicesAreNormalised() {
        service.update("languages", Map.of("languages.enabled", List.of("Java", "PYTHON", "java", " go ")), "admin");
        assertThat(service.getList("languages.enabled")).containsExactly("java", "python", "go");

        service.update("generation", Map.of("generation.sections", "api endpoints, overview", "generation.outputLanguage", "EN"), "admin");
        assertThat(service.getList("generation.sections")).containsExactly("API Endpoints", "Overview");
        assertThat(service.getString("generation.outputLanguage")).isEqualTo("en");
    }

    @Test
    void resetRestoresTheDefaultsOfTheGroupOnly() {
        service.update("retention", Map.of("retention.auditLogDays", 90, "retention.changeLogDays", 60), "admin");
        service.update("ai", Map.of("ai.tokenBudget", 8000), "admin");

        GroupView retention = service.reset("retention");

        assertThat(service.getInt("retention.auditLogDays")).isEqualTo(730);
        assertThat(service.getInt("retention.changeLogDays")).isEqualTo(365);
        assertThat(retention.settings()).allMatch(s -> !s.overridden());
        assertThat(service.getInt("ai.tokenBudget")).isEqualTo(8000);
    }

    @Test
    void unknownGroupIsNotFound() {
        assertThatThrownBy(() -> service.getGroup("billing"))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(error -> assertThat(((ResponseStatusException) error).getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND));
        assertThat(service.getGroup(" AI ").id()).isEqualTo("ai");
    }

    @Test
    void aCorruptedStoredValueFallsBackToTheDefault() {
        SystemSetting broken = new SystemSetting("ai.tokenBudget");
        broken.update("not-a-number", "someone");
        rows.put(broken.getKey(), broken);

        assertThat(service.getInt("ai.tokenBudget")).isEqualTo(4096);
    }

    @Test
    void secretsAreNeverPartOfTheConfiguration() {
        service.getAll().forEach(group -> group.settings().forEach(setting ->
                assertThat(setting.key().toLowerCase()).doesNotContain("secret", "password", "privatekey", "apikey")));
    }

    @Test
    void retentionAndGenerationAccessorsReflectPatchAndReset() {
    service.update("retention", Map.of("retention.auditLogDays", 90), "admin");
    assertThat(service.getAuditLogRetentionDays()).isEqualTo(90);

    service.update("generation", Map.of("generation.maxAttempts", 5), "admin");
    assertThat(service.getGenerationMaxAttempts()).isEqualTo(5);

    service.update("auto-update", Map.of("autoUpdate.enabled", true), "admin");
    assertThat(service.isAutoUpdateEnabled()).isTrue();

    service.reset("retention");
    service.reset("generation");
    service.reset("auto-update");
    assertThat(service.getAuditLogRetentionDays()).isEqualTo(730);
    assertThat(service.getGenerationMaxAttempts()).isEqualTo(3);
    assertThat(service.isAutoUpdateEnabled()).isFalse();
}

    @Test
    void retentionGenerationAndAutoUpdateAccessorsReflectPatchAndReset() {
        service.update("retention", Map.of("retention.auditLogDays", 90), "admin");
        assertThat(service.getAuditLogRetentionDays()).isEqualTo(90);

        service.update("generation", Map.of("generation.maxAttempts", 5), "admin");
        assertThat(service.getGenerationMaxAttempts()).isEqualTo(5);

        service.update("auto-update", Map.of("autoUpdate.enabled", true), "admin");
        assertThat(service.isAutoUpdateEnabled()).isTrue();

        service.reset("retention");
        service.reset("generation");
        service.reset("auto-update");
        assertThat(service.getAuditLogRetentionDays()).isEqualTo(730);
        assertThat(service.getGenerationMaxAttempts()).isEqualTo(3);
        assertThat(service.isAutoUpdateEnabled()).isFalse();
    }
    private void assertInvalid(String group, String key, Object value) {
        Map<String, Object> change = new HashMap<>();
        change.put(key, value);
        assertThatThrownBy(() -> service.update(group, change, "admin"))
                .as("%s = %s", key, value)
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(error -> assertThat(((ResponseStatusException) error).getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST));
    }
}

