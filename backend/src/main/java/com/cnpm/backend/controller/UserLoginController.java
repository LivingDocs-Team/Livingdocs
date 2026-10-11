
package com.cnpm.backend.controller;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import jakarta.validation.Valid;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.cnpm.backend.dto.LoginRequest;
import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;

@RestController
@RequestMapping("/api/auth")
public class UserLoginController {

    private final AuthenticationManager authenticationManager;
    private final UserRepository userRepository;

    public UserLoginController(
            AuthenticationManager authenticationManager,
            UserRepository userRepository) {
        this.authenticationManager = authenticationManager;
        this.userRepository = userRepository;
    }

    @PostMapping("/login")
    public ResponseEntity<?> login(
            @Valid @RequestBody LoginRequest request,
            HttpServletRequest httpRequest) {

        try {
            Authentication authentication =
                    authenticationManager.authenticate(
                            new UsernamePasswordAuthenticationToken(
                                    request.getEmail().trim().toLowerCase(),
                                    request.getPassword()
                            )
                    );

            SecurityContext context =
                    SecurityContextHolder.createEmptyContext();
            context.setAuthentication(authentication);
            SecurityContextHolder.setContext(context);

            HttpSession session = httpRequest.getSession(true);
            session.setAttribute(
                    HttpSessionSecurityContextRepository
                            .SPRING_SECURITY_CONTEXT_KEY,
                    context
            );

            User user = userRepository
                    .findByEmail(authentication.getName())
                    .orElseThrow();

            return ResponseEntity.ok(Map.of(
                    "message", "Login successful",
                    "id", user.getId(),
                    "email", user.getEmail(),
                    "username", user.getUsername(),
                    "firstName", user.getFirstName(),
                    "lastName", user.getLastName(),
                    "role", user.getRole()
            ));

        } catch (org.springframework.security.core.AuthenticationException ex) {
            SecurityContextHolder.clearContext();

            return ResponseEntity
                    .status(HttpStatus.UNAUTHORIZED)
                    .body(Map.of("message", "Invalid email or password"));
        }
    }
    @PostMapping("/logout")
public ResponseEntity<?> logout(
        HttpServletRequest request,
        HttpServletResponse response,
        Authentication authentication) {

    new SecurityContextLogoutHandler()
            .logout(request, response, authentication);

    return ResponseEntity.ok(
            Map.of("message", "Logout successful")
    );
}
}
