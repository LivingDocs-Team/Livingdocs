package com.cnpm.backend.repository;

import java.time.Instant;

import com.cnpm.backend.entity.AdminUserAudit;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface AdminUserAuditRepository extends Repository<AdminUserAudit, Long> {
    AdminUserAudit save(AdminUserAudit entry);
    Page<AdminUserAudit> findAll(Pageable pageable);

    @Modifying
    @Transactional
    @Query("delete from AdminUserAudit entry where entry.occurredAt < :cutoff")
    int deleteOlderThan(@Param("cutoff") Instant cutoff);
}
