package com.cnpm.backend.entity;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * LD-273: one overridden system setting. A setting without a row uses the default declared in
 * SystemConfigurationService, so the table only holds what an administrator has changed.
 * (Fields are called settingKey / settingValue because key and value are reserved words in HQL.)
 */
@Entity
@Table(name = "system_settings")
public class SystemSetting {
    @Id
    @Column(name = "setting_key", length = 100)
    private String settingKey;

    @Column(name = "setting_value", nullable = false, length = 4000)
    private String settingValue;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Column(name = "updated_by", length = 255)
    private String updatedBy;

    protected SystemSetting() { }

    public SystemSetting(String key) {
        this.settingKey = key;
        this.settingValue = "";
        this.updatedAt = Instant.now();
    }

    public void update(String value, String updatedBy) {
        this.settingValue = value;
        this.updatedBy = updatedBy;
        this.updatedAt = Instant.now();
    }

    public String getKey() { return settingKey; }
    public String getValue() { return settingValue; }
    public Instant getUpdatedAt() { return updatedAt; }
    public String getUpdatedBy() { return updatedBy; }
}

