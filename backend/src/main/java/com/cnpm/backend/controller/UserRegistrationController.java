
package com.cnpm.backend.controller;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.cnpm.backend.dto.RegisterRequest;
import com.cnpm.backend.entity.User;
import com.cnpm.backend.service.UserRegistrationService;

import jakarta.validation.Valid;

@RestController
@RequestMapping("/api/auth")
public class UserRegistrationController {

    private final UserRegistrationService registrationService;

    public UserRegistrationController(
            UserRegistrationService registrationService) {
        this.registrationService = registrationService;
    }

    @PostMapping("/register")
    public ResponseEntity<?> register(
            @Valid @RequestBody RegisterRequest request) {

        try {
            User user = registrationService.register(request);

            Map<String, Object> response = Map.of(
                    "message", "Registration successful",
                    "id", user.getId(),
                    "email", user.getEmail(),
                    "firstName", user.getFirstName(),
                    "lastName", user.getLastName(),
                    "role", user.getRole()
            );

            return ResponseEntity
                    .status(HttpStatus.CREATED)
                    .body(response);

        } catch (IllegalArgumentException e) {
            return ResponseEntity
                    .status(HttpStatus.CONFLICT)
                    .body(Map.of("message", e.getMessage()));
        }
    }
}
