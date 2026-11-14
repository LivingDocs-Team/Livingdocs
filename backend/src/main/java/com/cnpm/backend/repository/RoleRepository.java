package com.cnpm.backend.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.EntityGraph;
import java.util.Optional;
import com.cnpm.backend.entity.Role;

public interface RoleRepository extends JpaRepository<Role, String> {
    @EntityGraph(attributePaths = "permissions")
    Optional<Role> findWithPermissionsByName(String name);
}



