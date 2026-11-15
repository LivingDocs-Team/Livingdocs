package com.livingdocs.github.config;

import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@Configuration(proxyBeanMethods = false)
class DependencyHealthConfig {
    @Bean
    HealthIndicator aiServiceHealthIndicator(RestClient.Builder builder,
            @Value("${services.ai-service.base-url:http://localhost:8001}") String baseUrl) {
        return probe(healthClient(builder, baseUrl));
    }

    @Bean
    HealthIndicator codeAnalyzerHealthIndicator(RestClient.Builder builder,
            @Value("${services.code-analyzer.base-url:http://localhost:8000}") String baseUrl) {
        return probe(healthClient(builder, baseUrl));
    }

    private RestClient healthClient(RestClient.Builder builder, String baseUrl) {
        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(1));
        factory.setReadTimeout(Duration.ofSeconds(1));
        return builder.clone().baseUrl(baseUrl).requestFactory(factory).build();
    }

    static HealthIndicator probe(RestClient client) {
        return () -> {
            try {
                JsonNode body = client.get().uri("/health").retrieve().body(JsonNode.class);
                return body != null && "ok".equals(body.path("status").asText())
                        ? Health.up().build()
                        : Health.down().withDetail("reason", "Unexpected health status").build();
            } catch (RestClientException e) {
                return Health.down().withDetail("reason", "Health endpoint unavailable").build();
            }
        };
    }
}
