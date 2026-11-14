package com.livingdocs.github.repository;

import com.livingdocs.github.entity.WebhookDelivery;
import org.springframework.data.jpa.repository.JpaRepository;

public interface WebhookDeliveryRepository extends JpaRepository<WebhookDelivery, String> {
}



