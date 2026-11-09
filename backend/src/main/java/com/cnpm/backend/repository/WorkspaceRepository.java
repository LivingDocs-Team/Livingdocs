package com.cnpm.backend.repository;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import jakarta.persistence.LockModeType;

import com.cnpm.backend.entity.Workspace;

public interface WorkspaceRepository extends JpaRepository<Workspace, String> {

    List<Workspace> findAllByOwner_IdOrderByCreatedAtDescIdAsc(Long ownerId);

    Optional<Workspace> findByIdAndOwner_Id(String id, Long ownerId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select w from Workspace w where w.id = :id and w.owner.id = :ownerId")
    Optional<Workspace> findByIdAndOwnerIdForUpdate(@Param("id") String id, @Param("ownerId") Long ownerId);

    @org.springframework.data.jpa.repository.Query("""
            select w from Workspace w
            where w.owner.id = :userId
               or exists (select m.id from WorkspaceMembership m where m.workspace.id = w.id
                          and m.user.id = :userId and m.user.active = true)
            order by w.createdAt desc, w.id asc
            """)
    List<Workspace> findAllAccessibleByUserId(@org.springframework.data.repository.query.Param("userId") Long userId);
}
