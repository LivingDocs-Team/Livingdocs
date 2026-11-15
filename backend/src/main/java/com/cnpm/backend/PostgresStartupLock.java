package com.cnpm.backend;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;

final class PostgresStartupLock implements ApplicationContextInitializer<ConfigurableApplicationContext>, AutoCloseable {
    private static final Logger log = LoggerFactory.getLogger(PostgresStartupLock.class);
    private Connection connection;

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        var environment = context.getEnvironment();
        try {
            connection = DriverManager.getConnection(
                    environment.getRequiredProperty("spring.datasource.url"),
                    environment.getRequiredProperty("spring.datasource.username"),
                    environment.getRequiredProperty("spring.datasource.password"));
            log.info("Waiting for the PostgreSQL backend startup lock");
            try (var statement = connection.createStatement()) {
                // A separate session keeps the lock across migration, Hibernate DDL and application runners.
                // The schema migration uses (280, 1) on its own connection.
                statement.execute("SELECT pg_advisory_lock(280, 2)");
            }
            log.info("Acquired the PostgreSQL backend startup lock");
        } catch (SQLException exception) {
            throw new IllegalStateException("Could not acquire the PostgreSQL backend startup lock", exception);
        }
    }

    @Override
    public void close() throws SQLException {
        if (connection != null) {
            connection.close();
        }
    }
}
