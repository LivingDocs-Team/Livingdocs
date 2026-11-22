package com.cnpm.backend.service;

import java.time.Instant;
import java.time.temporal.ChronoUnit;

import com.cnpm.backend.repository.AdminUserAuditRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

@Configuration(proxyBeanMethods = false)
@EnableScheduling
public class AdminUserAuditRetention {
    private static final Logger log = LoggerFactory.getLogger(AdminUserAuditRetention.class);

    private final AdminUserAuditRepository audit;
    private final SystemConfigurationService config;

    public AdminUserAuditRetention(AdminUserAuditRepository audit, SystemConfigurationService config) {
        this.audit = audit;
        this.config = config;
    }

    @Scheduled(cron = "0 0 0 * * *", zone = "UTC")
    public void purgeExpiredRecords() {
        int retentionDays = config.getAuditLogRetentionDays();
        if (retentionDays <= 0) {
            log.warn("retention.auditLogDays={} is not positive; skipping admin-user audit purge", retentionDays);
            return;
        }
        Instant cutoff = Instant.now().minus(retentionDays, ChronoUnit.DAYS);
        int deleted = audit.deleteOlderThan(cutoff);
        log.info("Purged {} admin-user audit record(s) older than {} days (cutoff={})", deleted, retentionDays, cutoff);
    }
}