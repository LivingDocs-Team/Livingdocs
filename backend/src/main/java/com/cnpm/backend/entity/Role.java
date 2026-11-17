package com.cnpm.backend.entity;

import java.util.LinkedHashSet;
import java.util.Set;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.JoinTable;
import jakarta.persistence.ManyToMany;
import jakarta.persistence.Table;

@Entity
@Table(name = "roles")
public class Role {
    @Id
    @Column(length = 30)
    private String name;

    @Column(nullable = false, length = 120)
    private String description;

    @ManyToMany
    @JoinTable(name = "roles_permissions",
            joinColumns = @JoinColumn(name = "roles_name", referencedColumnName = "name"),
            inverseJoinColumns = @JoinColumn(name = "permissions_code", referencedColumnName = "code"))
    private Set<Permission> permissions = new LinkedHashSet<>();

    protected Role() { }

    public Role(String name, String description) {
        this.name = name;
        this.description = description;
    }

    public String getName() { return name; }
    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }
    public Set<Permission> getPermissions() { return permissions; }
}
