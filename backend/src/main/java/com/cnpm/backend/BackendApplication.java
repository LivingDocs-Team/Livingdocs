package com.cnpm.backend;

import java.sql.SQLException;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BackendApplication {

	public static void main(String[] args) throws SQLException {
		SpringApplication application = new SpringApplication(BackendApplication.class);
		try (var startupLock = new PostgresStartupLock()) {
			application.addInitializers(startupLock);
			application.run(args);
		}
	}

}
