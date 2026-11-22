package com.cnpm.backend.repository;

import org.springframework.data.jpa.repository.JpaRepository;

import com.cnpm.backend.entity.SystemSetting;

public interface SystemSettingRepository extends JpaRepository<SystemSetting, String> { }

