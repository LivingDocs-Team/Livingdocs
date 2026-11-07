package com.livingdocs.github.repository;

import com.livingdocs.github.entity.ConnectionStatus;
import com.livingdocs.github.entity.GitHubConnection;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

public interface GitHubConnectionRepository extends JpaRepository<GitHubConnection, UUID> {

    Optional<GitHubConnection> findByUserId(String userId);

    /**
     * Chỉ đổi trạng thái kết nối, không ghi lại token (LD-76): lưu cả bản ghi có thể ghi token cũ
     * đè lên token mà request khác vừa làm mới. Phải gọi trong transaction.
     */
    @Modifying(flushAutomatically = true)
    @Query("update GitHubConnection c set c.status = :status, c.updatedAt = :updatedAt where c.id = :id")
    int updateStatus(@Param("id") UUID id,
                     @Param("status") ConnectionStatus status,
                     @Param("updatedAt") Instant updatedAt);
}
