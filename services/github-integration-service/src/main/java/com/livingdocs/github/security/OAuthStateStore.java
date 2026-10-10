package com.livingdocs.github.security;

import org.springframework.stereotype.Component;

import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Lưu tham số "state" của luồng OAuth (chống tấn công CSRF) và nhớ state đó thuộc user nào.
 * Mỗi state chỉ dùng được 1 lần và hết hạn sau 10 phút.
 *
 * Bản này lưu trong bộ nhớ (đủ cho 1 instance). Khi chạy nhiều instance thì chuyển sang Redis.
 */
@Component
public class OAuthStateStore {

    static final Duration TTL = Duration.ofMinutes(10);

    private record Entry(String userId, Instant expiresAt) {
    }

    private final Map<String, Entry> states = new ConcurrentHashMap<>();
    private final SecureRandom random = new SecureRandom();
    private final Clock clock;

    public OAuthStateStore() {
        this(Clock.systemUTC());
    }

    OAuthStateStore(Clock clock) {
        this.clock = clock;
    }

    public String create(String userId) {
        removeExpired();
        byte[] bytes = new byte[24];
        random.nextBytes(bytes);
        String state = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        states.put(state, new Entry(userId, clock.instant().plus(TTL)));
        return state;
    }

    /** Trả về userId nếu state hợp lệ, đồng thời xoá state (chỉ dùng 1 lần). */
    public Optional<String> consume(String state) {
        if (state == null) {
            return Optional.empty();
        }
        Entry entry = states.remove(state);
        if (entry == null || entry.expiresAt().isBefore(clock.instant())) {
            return Optional.empty();
        }
        return Optional.of(entry.userId());
    }

    private void removeExpired() {
        Instant now = clock.instant();
        states.entrySet().removeIf(e -> e.getValue().expiresAt().isBefore(now));
    }
}
