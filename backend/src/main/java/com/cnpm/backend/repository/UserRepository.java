
package com.cnpm.backend.repository;

import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import org.springframework.data.jpa.repository.JpaRepository;

import com.cnpm.backend.entity.User;

public interface UserRepository extends JpaRepository<User, Long> {

    Optional<User> findByEmail(String email);

    Optional<User> findByGithubId(String githubId);

    boolean existsByEmail(String email);

    boolean existsByUsername(String username);

    @Query("""
            select u from User u
            where (:search is null or
                   lower(u.username) like lower(concat('%', :search, '%')) or
                   lower(u.email) like lower(concat('%', :search, '%')))
              and (:role is null or u.role = :role)
              and (:active is null or u.active = :active)
            """)
    Page<User> searchForAdministration(
            @Param("search") String search,
            @Param("role") String role,
            @Param("active") Boolean active,
            Pageable pageable);
}
