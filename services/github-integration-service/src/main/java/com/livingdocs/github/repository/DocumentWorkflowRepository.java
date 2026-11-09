package com.livingdocs.github.repository;

import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import com.livingdocs.github.entity.DocumentWorkflow;
import com.livingdocs.github.entity.DocumentWorkflowStatus;

import jakarta.persistence.LockModeType;

@Repository
public interface DocumentWorkflowRepository extends JpaRepository<DocumentWorkflow, UUID> {
    boolean existsByDocumentId(String documentId);
    Page<DocumentWorkflow> findByOwnerUserIdOrderByCreatedAtDesc(String ownerUserId, Pageable pageable);
    Page<DocumentWorkflow> findByStatusOrderBySubmittedAtAsc(DocumentWorkflowStatus status, Pageable pageable);

    @Query("""
            select w from DocumentWorkflow w
            where (:includeOwned = true and w.ownerUserId = :actor)
               or (:includeStaffQueue = true and (
                    (w.status = :pendingStaff or w.status = :staffReviewing)
                    and (w.reviewerUserId is null or w.reviewerUserId = :actor)
               ))
               or (:includeAssignedReviews = true and w.reviewerUserId = :actor)
               or (:includeManagerDecisions = true and w.status in :managerStatuses)
            """)
    Page<DocumentWorkflow> findHistoryAccessible(@Param("actor") String actor,
            @Param("includeOwned") boolean includeOwned,
            @Param("includeStaffQueue") boolean includeStaffQueue,
            @Param("includeAssignedReviews") boolean includeAssignedReviews,
            @Param("includeManagerDecisions") boolean includeManagerDecisions,
            @Param("pendingStaff") DocumentWorkflowStatus pendingStaff,
            @Param("staffReviewing") DocumentWorkflowStatus staffReviewing,
            @Param("managerStatuses") java.util.Collection<DocumentWorkflowStatus> managerStatuses,
            Pageable pageable);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select w from DocumentWorkflow w where w.id = :id")
    java.util.Optional<DocumentWorkflow> lockById(@Param("id") UUID id);

    @Query("select w from DocumentWorkflow w where w.status = :pending "
            + "or (w.status = :reviewing and w.reviewerUserId = :reviewer)")
    Page<DocumentWorkflow> staffQueue(@Param("pending") DocumentWorkflowStatus pending,
            @Param("reviewing") DocumentWorkflowStatus reviewing,
            @Param("reviewer") String reviewer, Pageable pageable);
}
