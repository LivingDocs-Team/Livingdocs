package com.cnpm.backend.service;

import java.time.Instant;
import java.time.temporal.ChronoUnit;

import com.cnpm.backend.repository.AdminUserAuditRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

@Configuration(proxyBeanMethods = false)
@EnableScheduling
public class AdminUserAuditRetention {
    private final AdminUserAuditRepository audit;
    private final int retentionDays;

    public AdminUserAuditRetention(AdminUserAuditRepository audit,
            @Value("${app.admin-user-audit.retention-days}") int retentionDays) {
        if (retentionDays < 0) {
            throw new IllegalArgumentException("Admin user audit retention days must be non-negative");
        }
        this.audit = audit;
        this.retentionDays = retentionDays;
    }

    @Scheduled(cron = "0 0 0 * * *", zone = "UTC")
    void purgeExpiredRecords() {
        if (retentionDays > 0) {
            audit.deleteOlderThan(Instant.now().minus(retentionDays, ChronoUnit.DAYS));
        }
    }
}
