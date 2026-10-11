
package com.cnpm.backend.repository;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

import com.cnpm.backend.entity.User;

public interface UserRepository extends JpaRepository<User, Long> {

    Optional<User> findByEmail(String email);

    Optional<User> findByGithubId(String githubId);

    boolean existsByEmail(String email);

    boolean existsByUsername(String username);
}
