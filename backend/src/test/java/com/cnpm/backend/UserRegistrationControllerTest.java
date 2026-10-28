package com.cnpm.backend;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

import com.cnpm.backend.controller.UserRegistrationController;
import com.cnpm.backend.dto.RegisterRequest;
import com.cnpm.backend.entity.User;
import com.cnpm.backend.service.UserRegistrationService;

@ExtendWith(MockitoExtension.class)
class UserRegistrationControllerTest {

    @Mock
    private UserRegistrationService registrationService;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        LocalValidatorFactoryBean validator = new LocalValidatorFactoryBean();
        validator.afterPropertiesSet();
        mockMvc = MockMvcBuilders
                .standaloneSetup(
                        new UserRegistrationController(registrationService))
                .setValidator(validator)
                .build();
    }

    @Test
    void registersValidRequestAndReturnsCreatedUserFields() throws Exception {
        User user = new User(
                "alex@example.com", "encoded", "Alex", "Smith",
                "DEVELOPER", true);
        user.setUsername("alexsmith");
        ReflectionTestUtils.setField(user, "id", 42L);
        when(registrationService.register(any(RegisterRequest.class)))
                .thenReturn(user);

        mockMvc.perform(post("/api/auth/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "username": "alexsmith",
                          "email": "alex@example.com",
                          "password": "test-password-value",
                          "firstName": "Alex",
                          "lastName": "Smith"
                        }
                        """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.message").value("Registration successful"))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.email").value("alex@example.com"))
                .andExpect(jsonPath("$.firstName").value("Alex"))
                .andExpect(jsonPath("$.lastName").value("Smith"))
                .andExpect(jsonPath("$.role").value("DEVELOPER"));

        verify(registrationService).register(any(RegisterRequest.class));
    }

    @Test
    void returnsConflictWhenUsernameOrEmailIsAlreadyRegistered()
            throws Exception {
        when(registrationService.register(any(RegisterRequest.class)))
                .thenThrow(new IllegalArgumentException(
                        "Email is already registered"));

        mockMvc.perform(post("/api/auth/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "username": "alexsmith",
                          "email": "alex@example.com",
                          "password": "test-password-value",
                          "firstName": "Alex",
                          "lastName": "Smith"
                        }
                        """))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.message")
                        .value("Email is already registered"));
    }

    @Test
    void rejectsInvalidRequestBeforeCallingRegistrationService()
            throws Exception {
        mockMvc.perform(post("/api/auth/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "username": "ab",
                          "email": "not-an-email",
                          "password": "short",
                          "firstName": "",
                          "lastName": "Smith"
                        }
                        """))
                .andExpect(status().isBadRequest());

        verify(registrationService, never())
                .register(any(RegisterRequest.class));
    }
}