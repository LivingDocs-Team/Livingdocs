package com.livingdocs.github.config;

import org.springframework.boot.autoconfigure.flyway.FlywayConfigurationCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import javax.sql.DataSource;

@Configuration
public class FlywayMigrationLineageConfig {

    @Bean
    FlywayConfigurationCustomizer flywayMigrationLineageCustomizer(
            DataSource dataSource, FlywayMigrationLineageSelector selector) {
        return configuration -> configuration.locations(selector.select(dataSource).location());
    }
}
