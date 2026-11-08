package com.cnpm.backend.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import com.cnpm.backend.entity.Permission;

public interface PermissionRepository extends JpaRepository<Permission, String> { }
