package com.cnpm.backend;

import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;
import com.cnpm.backend.service.CustomUserDetailsService;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.userdetails.UserDetails;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class CustomUserDetailsServiceTest {

    @Test
    void disabledAccountIsNotEnabledForPasswordAuthentication() {
        UserRepository repository = mock(UserRepository.class);
        User account = new User("disabled@example.test", "encoded-password",
                "Disabled", "User", "DEVELOPER", true);
        account.setActive(false);
        when(repository.findByEmail("disabled@example.test"))
                .thenReturn(Optional.of(account));

        UserDetails details = new CustomUserDetailsService(repository)
                .loadUserByUsername("disabled@example.test");

        assertThat(details.isEnabled()).isFalse();
    }

    @Test
    void newAndExistingAccountsRemainEnabledByDefault() {
        UserRepository repository = mock(UserRepository.class);
        User account = new User("active@example.test", "encoded-password",
                "Active", "User", "DEVELOPER", true);
        when(repository.findByEmail("active@example.test"))
                .thenReturn(Optional.of(account));

        UserDetails details = new CustomUserDetailsService(repository)
                .loadUserByUsername("active@example.test");

        assertThat(details.isEnabled()).isTrue();
    }
}
