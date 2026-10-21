package com.livingdocs.github.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

import java.time.Duration;

@Configuration
public class DocumentationServiceConfig {

    @Bean("codeAnalyzerRestClient")
    RestClient codeAnalyzerRestClient(
            RestClient.Builder builder,
            @Value("${services.code-analyzer.base-url:http://localhost:8000}") String baseUrl) {
        return builder.clone().baseUrl(baseUrl).requestFactory(requestFactory()).build();
    }

    @Bean("aiServiceRestClient")
    RestClient aiServiceRestClient(
            RestClient.Builder builder,
            @Value("${services.ai-service.base-url:http://localhost:8001}") String baseUrl) {
        return builder.clone().baseUrl(baseUrl).requestFactory(requestFactory()).build();
    }

    private SimpleClientHttpRequestFactory requestFactory() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(5));
        factory.setReadTimeout(Duration.ofSeconds(120));
        return factory;
    }
}
