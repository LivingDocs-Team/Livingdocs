package com.cnpm.backend.config;

import java.time.Duration;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.HealthIndicator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@Configuration(proxyBeanMethods = false)
class IntegrationHealthConfig {
    @Bean
    HealthIndicator githubIntegrationHealthIndicator(RestClient.Builder builder,
            @Value("${services.github-integration.base-url:http://localhost:8082}") String baseUrl) {
        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(1));
        factory.setReadTimeout(Duration.ofSeconds(5));
        return probe(builder.clone().baseUrl(baseUrl).requestFactory(factory).build());
    }

    static HealthIndicator probe(RestClient client) {
        return () -> {
            try {
                Map<?, ?> body = client.get().uri("/actuator/health").retrieve().body(Map.class);
                return body != null && "UP".equals(body.get("status"))
                        ? Health.up().build()
                        : Health.down().withDetail("reason", "Unexpected health status").build();
            } catch (RestClientException e) {
                return Health.down().withDetail("reason", "Integration health endpoint unavailable or unhealthy").build();
            }
        };
    }
}
