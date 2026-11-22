package com.cnpm.backend;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.context.PropertyPlaceholderAutoConfiguration;
import org.springframework.boot.convert.ApplicationConversionService;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import com.cnpm.backend.controller.AdminSystemConfigController;
import com.cnpm.backend.service.SystemConfigurationService;

class AdminSystemConfigControllerTest {

    private static final String CLIENT_ID = "spring.security.oauth2.client.registration.github.client-id";

    // Strict placeholders and Boot conversions ("5s" -> Duration) as in the application; the controller alone.
    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withInitializer(context -> context.getBeanFactory()
                    .setConversionService(ApplicationConversionService.getSharedInstance()))
            .withConfiguration(AutoConfigurations.of(PropertyPlaceholderAutoConfiguration.class))
            .withBean(SystemConfigurationService.class, () -> mock(SystemConfigurationService.class))
            .withUserConfiguration(AdminSystemConfigController.class);

    private static boolean oauthConfigured(org.springframework.context.ApplicationContext context) {
        return context.getBean(AdminSystemConfigController.class).getConfig().security().githubOAuthConfigured();
    }

    @Test
    void startsWhenTheOAuthClientIdPointsToAnUnsetVariable() {
        // application.properties: client-id=${SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_GITHUB_CLIENT_ID} (CI sets none)
        runner.withPropertyValues(CLIENT_ID + "=${LD316_TEST_UNSET_GITHUB_CLIENT_ID}").run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(oauthConfigured(context)).isFalse();
        });
    }

    @Test
    void reportsWhetherTheOAuthClientIsConfigured() {
        runner.withPropertyValues(CLIENT_ID + "=Iv1.abc123").run(context -> assertThat(oauthConfigured(context)).isTrue());
        runner.withPropertyValues(CLIENT_ID + "=local-placeholder").run(context -> assertThat(oauthConfigured(context)).isFalse());
        runner.withPropertyValues(CLIENT_ID + "=").run(context -> assertThat(oauthConfigured(context)).isFalse());
        runner.run(context -> assertThat(oauthConfigured(context)).isFalse());
    }
}
