package com.livingdocs.github.dto;

import java.time.Instant;

/** Trạng thái kết nối GitHub. Không bao giờ trả token ra ngoài. */
public record ConnectionResponse(
        boolean connected,
        String githubLogin,
        String status,
        Instant connectedAt,
        Instant tokenExpiresAt) {

    public static ConnectionResponse notConnected() {
        return new ConnectionResponse(false, null, "NOT_CONNECTED", null, null);
    }
}
