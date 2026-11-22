package com.cnpm.backend.service;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.time.Instant;
import java.time.temporal.ChronoUnit;

import com.cnpm.backend.repository.AdminUserAuditRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class AdminUserAuditRetentionTest {

    @Mock AdminUserAuditRepository audit;
    @Mock SystemConfigurationService config;

    @InjectMocks AdminUserAuditRetention retention;

    @Test
    void purgeUsesConfiguredRetentionWindow() {
        when(config.getAuditLogRetentionDays()).thenReturn(90);
        when(audit.deleteOlderThan(any())).thenReturn(5);

        retention.purgeExpiredRecords();

        verify(audit).deleteOlderThan(argThat(cutoff ->
                Math.abs(ChronoUnit.DAYS.between(cutoff, Instant.now()) - 90) <= 1));
    }

    @Test
    void purgeReadsOverrideOnEveryRun() {
        when(config.getAuditLogRetentionDays()).thenReturn(730, 30);
        when(audit.deleteOlderThan(any())).thenReturn(0);

        retention.purgeExpiredRecords();   // default 730
        retention.purgeExpiredRecords();   // admin just PATCHed to 30

        verify(audit).deleteOlderThan(argThat(cutoff ->
                Math.abs(ChronoUnit.DAYS.between(cutoff, Instant.now()) - 730) <= 1));
        verify(audit).deleteOlderThan(argThat(cutoff ->
                Math.abs(ChronoUnit.DAYS.between(cutoff, Instant.now()) - 30) <= 1));
    }

    @Test
    void purgeSkipsWhenRetentionIsNotPositive() {
        when(config.getAuditLogRetentionDays()).thenReturn(0);

        retention.purgeExpiredRecords();

        verifyNoInteractions(audit);
    }
}