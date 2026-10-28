package com.cnpm.backend;

import com.cnpm.backend.controller.UserLoginController;
import com.cnpm.backend.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.AuthenticationManager;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

class UserLoginLogoutTest {

    @Test
    void logoutInvalidatesBackendSession() {
        UserLoginController controller = new UserLoginController(
                mock(AuthenticationManager.class), mock(UserRepository.class));
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpSession session = new MockHttpSession();
        request.setSession(session);

        controller.logout(request, new MockHttpServletResponse(), null);

        assertThat(session.isInvalid()).isTrue();
    }
}
