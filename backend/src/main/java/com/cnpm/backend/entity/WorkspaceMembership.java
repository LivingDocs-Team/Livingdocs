package com.cnpm.backend.entity;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(name = "workspace_memberships", uniqueConstraints = @UniqueConstraint(
        name = "uk_workspace_membership_workspace_user", columnNames = {"workspace_id", "user_id"}))
public class WorkspaceMembership {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "workspace_id", nullable = false)
    private Workspace workspace;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    protected WorkspaceMembership() { }

    public WorkspaceMembership(Workspace workspace, User user) {
        this.workspace = workspace;
        this.user = user;
    }

    public Long getId() { return id; }
    public Workspace getWorkspace() { return workspace; }
    public User getUser() { return user; }
}
