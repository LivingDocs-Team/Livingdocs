
package com.cnpm.backend.service;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.cnpm.backend.dto.RegisterRequest;
import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;

@Service
public class UserRegistrationService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;

    public UserRegistrationService(
            UserRepository userRepository,
            PasswordEncoder passwordEncoder) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
    }

    @Transactional
    public User register(RegisterRequest request) {
        String username = request.getUsername().trim();
        String email = request.getEmail().trim().toLowerCase();

        if (userRepository.existsByUsername(username)) {
            throw new IllegalArgumentException(
                    "Username is already registered");
        }

        if (userRepository.existsByEmail(email)) {
            throw new IllegalArgumentException(
                    "Email is already registered");
        }

        User user = new User(
                email,
                passwordEncoder.encode(request.getPassword()),
                request.getFirstName().trim(),
                request.getLastName().trim(),
                "DEVELOPER",
                true
        );

        user.setUsername(username);

        return userRepository.save(user);
    }
}
