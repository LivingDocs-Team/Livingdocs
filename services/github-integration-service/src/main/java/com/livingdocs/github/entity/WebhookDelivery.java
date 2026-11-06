package com.livingdocs.github.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.Instant;

/** LD-68: một webhook GitHub đã xử lý, nhận diện bằng header X-GitHub-Delivery (GitHub gửi lại thì bỏ qua). */
@Entity
@Table(name = "github_webhook_deliveries")
public class WebhookDelivery {

    @Id
    @Column(name = "delivery_id", nullable = false, length = 100)
    private String deliveryId;

    @Column(nullable = false, length = 50)
    private String event;

    @Column(name = "github_repo_id", nullable = false)
    private Long githubRepoId;

    @Column(name = "received_at", nullable = false)
    private Instant receivedAt;

    protected WebhookDelivery() {
    }

    public WebhookDelivery(String deliveryId, String event, Long githubRepoId) {
        this.deliveryId = deliveryId;
        this.event = event;
        this.githubRepoId = githubRepoId;
        this.receivedAt = Instant.now();
    }

    public String getDeliveryId() { return deliveryId; }
    public String getEvent() { return event; }
    public Long getGithubRepoId() { return githubRepoId; }
    public Instant getReceivedAt() { return receivedAt; }
}
