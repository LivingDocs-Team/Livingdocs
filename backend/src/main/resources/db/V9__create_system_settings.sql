-- LD-273: administrator overrides for system configuration.
-- Replaces the implicit table previously created by Hibernate ddl-auto=update so upgrades run
-- deterministically on PostgreSQL with existing data.

CREATE TABLE IF NOT EXISTS system_settings (
    setting_key   VARCHAR(100)             PRIMARY KEY,
    setting_value VARCHAR(4000)            NOT NULL,
    updated_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_by    VARCHAR(255)
);

COMMENT ON TABLE  system_settings               IS 'LD-273: admin overrides for SystemConfigurationService; missing key = catalog default';
COMMENT ON COLUMN system_settings.setting_key   IS 'Setting key from SystemConfigurationService.CATALOG';
COMMENT ON COLUMN system_settings.setting_value IS 'Encoded value: string, integer, decimal, boolean, or comma-separated list';
COMMENT ON COLUMN system_settings.updated_at    IS 'Last PATCH time (UTC)';
COMMENT ON COLUMN system_settings.updated_by    IS 'Actor (admin username) that last PATCHed the setting';