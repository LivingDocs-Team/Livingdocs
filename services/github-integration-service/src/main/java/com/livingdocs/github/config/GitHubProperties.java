package com.livingdocs.github.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Thông tin GitHub App, đọc từ application.yml / file .env.
 *
 * @param clientId     Client ID của GitHub App (dạng Iv23li...)
 * @param clientSecret Client secret của GitHub App
 * @param appSlug      tên app trên URL, ví dụ livingdocs-dev-hai
 * @param redirectUri  phải trùng với "Redirect URI" đã khai báo trên GitHub
 * @param oauthBaseUrl https://github.com (đổi được khi test)
 * @param apiBaseUrl   https://api.github.com (đổi được khi test)
 */
@ConfigurationProperties(prefix = "github")
public record GitHubProperties(
        String clientId,
        String clientSecret,
        String appSlug,
        String redirectUri,
        String oauthBaseUrl,
        String apiBaseUrl) {
}
