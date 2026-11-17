package com.cnpm.backend.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.Lock;
import jakarta.persistence.LockModeType;
import java.util.Optional;
import com.cnpm.backend.entity.Role;

public interface RoleRepository extends JpaRepository<Role, String> {
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    Optional<Role> findForUpdateByName(String name);

    @EntityGraph(attributePaths = "permissions")
    Optional<Role> findWithPermissionsByName(String name);
}
