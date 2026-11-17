package com.cnpm.backend;

import java.util.UUID;

import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.PageRequest;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Runs against PostgreSQL like the other *PostgresTest classes. The administrator user list is
 * queried without a search term: PostgreSQL used to answer 500 ("function lower(bytea) does not exist")
 * because the null search parameter was sent as bytea.
 */
@SpringBootTest
@Transactional
class UserRepositoryPostgresTest {
    @Autowired UserRepository users;

    @Test
    void administratorListWorksWithoutAnyFilter() {
        String tag = UUID.randomUUID().toString().substring(0, 8);
        users.save(account("dev", tag, "DEVELOPER"));
        users.save(account("staff", tag, "STAFF"));

        var page = users.searchForAdministration(null, null, null, PageRequest.of(0, 100));

        assertThat(page.getContent()).extracting(User::getEmail)
                .contains("dev." + tag + "@example.test", "staff." + tag + "@example.test");
    }

    @Test
    void searchMatchesUsernameOrEmailIgnoringCaseAndCombinesWithRoleFilter() {
        String tag = UUID.randomUUID().toString().substring(0, 8);
        users.save(account("dev", tag, "DEVELOPER"));
        users.save(account("staff", tag, "STAFF"));

        var byEmail = users.searchForAdministration(("STAFF." + tag).toUpperCase(), null, null, PageRequest.of(0, 20));
        assertThat(byEmail.getContent()).extracting(User::getEmail).containsExactly("staff." + tag + "@example.test");

        var byUsername = users.searchForAdministration("dev_" + tag, null, null, PageRequest.of(0, 20));
        assertThat(byUsername.getContent()).extracting(User::getRole).containsExactly("DEVELOPER");

        var wrongRole = users.searchForAdministration(tag, "MANAGER", null, PageRequest.of(0, 20));
        assertThat(wrongRole.getContent()).isEmpty();

        var activeStaff = users.searchForAdministration(tag, "STAFF", true, PageRequest.of(0, 20));
        assertThat(activeStaff.getContent()).extracting(User::getUsername).containsExactly("staff_" + tag);
    }

    private static User account(String kind, String tag, String role) {
        User user = new User();
        user.setUsername(kind + "_" + tag);
        user.setEmail(kind + "." + tag + "@example.test");
        user.setPassword("not-a-real-hash");
        user.setFirstName("Test");
        user.setLastName("User");
        user.setRole(role);
        return user;
    }
}
