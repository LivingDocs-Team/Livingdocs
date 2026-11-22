package com.livingdocs.github.config;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.web.client.RestClient;

import java.time.Duration;

@Configuration
public class DocumentationServiceConfig {

    @Bean("codeAnalyzerRestClient")
    RestClient codeAnalyzerRestClient(
            RestClient.Builder builder,
            @Value("${services.code-analyzer.base-url:http://localhost:8000}") String baseUrl) {
        return builder.clone().baseUrl(baseUrl).requestFactory(requestFactory(Duration.ofSeconds(120))).build();
    }

    @Bean("aiServiceRestClient")
    RestClient aiServiceRestClient(
            RestClient.Builder builder,
            @Value("${services.ai-service.base-url:http://localhost:8001}") String baseUrl,
            @Value("${security.internal-api-secret:}") String internalSecret) {
        RestClient.Builder client = builder.clone().baseUrl(baseUrl).requestFactory(requestFactory(Duration.ofSeconds(120)));
        if (internalSecret != null && !internalSecret.isBlank()) {
            client.defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer " + internalSecret);
        }
        return client.build();
    }

    @Bean("revisionAiRestClient")
    RestClient revisionAiRestClient(@Qualifier("aiServiceRestClient")
                                    RestClient aiService) {
        return aiService.mutate().requestFactory(requestFactory(Duration.ofMinutes(45))).build();
    }

    private SimpleClientHttpRequestFactory requestFactory(Duration readTimeout) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(5));
        factory.setReadTimeout(readTimeout);
        return factory;
    }
}
