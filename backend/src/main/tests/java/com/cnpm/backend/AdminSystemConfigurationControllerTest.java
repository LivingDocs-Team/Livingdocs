package com.cnpm.backend;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.server.ResponseStatusException;

import com.cnpm.backend.controller.AdminSystemConfigurationController;
import com.cnpm.backend.service.SystemConfigurationService;
import com.cnpm.backend.service.SystemConfigurationService.GroupView;

class AdminSystemConfigurationControllerTest {
    private final SystemConfigurationService service = mock(SystemConfigurationService.class);
    private final AdminSystemConfigurationController controller = new AdminSystemConfigurationController(service);

    @Test
    void updateRecordsTheAuthenticatedAdministrator() {
        Authentication authentication = mock(Authentication.class);
        when(authentication.getName()).thenReturn("admin");
        GroupView group = new GroupView("ai", "AI Model & Confidence", List.of());
        Map<String, Object> change = Map.of("ai.tokenBudget", 8000);
        when(service.update("ai", change, "admin")).thenReturn(group);

        assertThat(controller.updateGroup("ai", new AdminSystemConfigurationController.UpdateRequest(change), authentication))
                .isSameAs(group);
        verify(service).update("ai", change, "admin");
    }

    @Test
    void updateRequiresASettingsBody() {
        assertThatThrownBy(() -> controller.updateGroup("ai", new AdminSystemConfigurationController.UpdateRequest(null),
                mock(Authentication.class)))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(error -> assertThat(((ResponseStatusException) error).getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST));
    }

    @Test
    void readingNeedsViewPermissionAndChangingNeedsUpdatePermission() throws Exception {
        assertThat(authority("listGroups")).isEqualTo("hasAuthority('SYSTEM_CONFIG_VIEW')");
        assertThat(authority("getGroup", String.class)).isEqualTo("hasAuthority('SYSTEM_CONFIG_VIEW')");
        assertThat(authority("updateGroup", String.class, AdminSystemConfigurationController.UpdateRequest.class,
                Authentication.class)).isEqualTo("hasAuthority('SYSTEM_CONFIG_UPDATE')");
        assertThat(authority("resetGroup", String.class)).isEqualTo("hasAuthority('SYSTEM_CONFIG_UPDATE')");
    }

    private static String authority(String method, Class<?>... parameters) throws Exception {
        return AdminSystemConfigurationController.class.getMethod(method, parameters)
                .getAnnotation(PreAuthorize.class).value();
    }
}

