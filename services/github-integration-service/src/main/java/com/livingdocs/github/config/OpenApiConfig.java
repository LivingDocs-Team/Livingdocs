package com.livingdocs.github.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI livingDocsOpenApi() {
        return new OpenAPI().info(new Info()
                .title("LivingDocs - GitHub Integration Service")
                .version("0.1.0")
                .description("""
                        Epic 2 (GitHub Account Connection) và Epic 3 (Repository Management).

                        Tạm thời người dùng được xác định bằng header `X-User-Id`.
                        Khi service đăng nhập của TV1 xong, header này sẽ được thay bằng JWT.
                        """));
    }
}
