package com.livingdocs.github;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class GithubIntegrationServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(GithubIntegrationServiceApplication.class, args);
    }
}
