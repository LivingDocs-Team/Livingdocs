package com.cnpm.backend.service;

import java.time.Instant;
import java.time.temporal.ChronoUnit;

import com.cnpm.backend.repository.AdminUserAuditRepository;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIllegalArgumentException;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class AdminUserAuditRetentionTest {
    private final AdminUserAuditRepository audit = mock(AdminUserAuditRepository.class);

    @Test
    void zeroDaysDisablesDeletion() {
        new AdminUserAuditRetention(audit, 0).purgeExpiredRecords();

        verifyNoInteractions(audit);
    }

    @Test
    void positiveDaysSetTheCutoff() {
        Instant earliest = Instant.now().minus(30, ChronoUnit.DAYS);

        new AdminUserAuditRetention(audit, 30).purgeExpiredRecords();

        var cutoff = ArgumentCaptor.forClass(Instant.class);
        verify(audit).deleteOlderThan(cutoff.capture());
        assertThat(cutoff.getValue()).isBetween(earliest, Instant.now().minus(30, ChronoUnit.DAYS));
    }

    @Test
    void negativeDaysAreRejected() {
        assertThatIllegalArgumentException().isThrownBy(() -> new AdminUserAuditRetention(audit, -1));
        verifyNoInteractions(audit);
    }
}
