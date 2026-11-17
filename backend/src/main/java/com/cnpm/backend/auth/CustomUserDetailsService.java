
package com.cnpm.backend.auth;

import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;

import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;
import com.cnpm.backend.repository.RoleRepository;

@Service
public class CustomUserDetailsService implements UserDetailsService {

    private final UserRepository userRepository;
    private final RoleRepository roleRepository;

    @Autowired
    public CustomUserDetailsService(UserRepository userRepository, RoleRepository roleRepository) {
        this.userRepository = userRepository;
        this.roleRepository = roleRepository;
    }

    public CustomUserDetailsService(UserRepository userRepository) {
        this(userRepository, null);
    }

    @Override
    public UserDetails loadUserByUsername(String email)
            throws UsernameNotFoundException {

        User user = userRepository.findByEmail(email.trim().toLowerCase())
                .orElseThrow(() ->
                        new UsernameNotFoundException("Invalid email or password"));

        var authorities = new java.util.ArrayList<org.springframework.security.core.GrantedAuthority>();
        String roleName = user.getRole().startsWith("ROLE_") ? user.getRole().substring(5) : user.getRole();
        authorities.add(new SimpleGrantedAuthority("ROLE_" + roleName));
        if (roleRepository != null) {
            roleRepository.findWithPermissionsByName(roleName).ifPresent(role -> role.getPermissions()
                    .forEach(permission -> authorities.add(new SimpleGrantedAuthority(permission.getCode()))));
        }
        var builder = org.springframework.security.core.userdetails.User
                .withUsername(user.getEmail())
                .password(user.getPassword())
                .authorities(authorities)
                .disabled(!user.isActive());
        return builder.build();
    }
}
