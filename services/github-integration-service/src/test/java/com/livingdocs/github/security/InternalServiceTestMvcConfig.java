package com.livingdocs.github.security;

import org.springframework.boot.test.autoconfigure.web.servlet.MockMvcBuilderCustomizer;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

@TestConfiguration
public class InternalServiceTestMvcConfig {

    @Bean
    MockMvcBuilderCustomizer internalServiceCredentialForIntegrationTests() {
        return builder -> builder.defaultRequest(get("/")
                .header(HttpHeaders.AUTHORIZATION, "Bearer test-only-internal-credential"));
    }
}
