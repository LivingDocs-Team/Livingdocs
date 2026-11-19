package com.livingdocs.github.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import java.util.Arrays;

/**
 * Cho phép frontend chạy ở địa chỉ khác (ví dụ http://localhost:3000) gọi API của service này từ trình duyệt.
 * Danh sách địa chỉ lấy từ {@code app.cors.allowed-origins} (biến môi trường {@code CORS_ALLOWED_ORIGINS}),
 * cách nhau bởi dấu phẩy. Để trống thì không cho phép địa chỉ nào.
 */
@Configuration
public class CorsConfig implements WebMvcConfigurer {

    private final String[] allowedOrigins;

    public CorsConfig(@Value("${app.cors.allowed-origins:}") String allowedOrigins) {
        this.allowedOrigins = Arrays.stream(allowedOrigins.split(","))
                .map(String::trim)
                .filter(origin -> !origin.isEmpty())
                .toArray(String[]::new);
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        if (allowedOrigins.length == 0) {
            return;
        }
        registry.addMapping("/api/**")
                .allowedOrigins(allowedOrigins)
                .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
                .allowedHeaders("*")
                // để frontend đọc được thời gian chờ khi bị rate limit (429)
                .exposedHeaders("Retry-After")
                .maxAge(3600);
    }
}
