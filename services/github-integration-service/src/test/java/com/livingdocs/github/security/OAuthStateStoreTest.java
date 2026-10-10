package com.livingdocs.github.security;

import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import static org.assertj.core.api.Assertions.assertThat;

class OAuthStateStoreTest {

    @Test
    void stateCanBeUsedOnlyOnce() {
        OAuthStateStore store = new OAuthStateStore();
        String state = store.create("user-1");

        assertThat(store.consume(state)).contains("user-1");
        assertThat(store.consume(state)).isEmpty();
    }

    @Test
    void unknownStateIsRejected() {
        assertThat(new OAuthStateStore().consume("khong-ton-tai")).isEmpty();
        assertThat(new OAuthStateStore().consume(null)).isEmpty();
    }

    @Test
    void expiredStateIsRejected() {
        MutableClock clock = new MutableClock(Instant.parse("2026-10-10T10:00:00Z"));
        OAuthStateStore store = new OAuthStateStore(clock);
        String state = store.create("user-1");

        clock.now = clock.now.plus(OAuthStateStore.TTL).plus(Duration.ofSeconds(1));

        assertThat(store.consume(state)).isEmpty();
    }

    private static final class MutableClock extends Clock {
        Instant now;

        MutableClock(Instant now) { this.now = now; }

        @Override public ZoneOffset getZone() { return ZoneOffset.UTC; }
        @Override public Clock withZone(java.time.ZoneId zone) { return this; }
        @Override public Instant instant() { return now; }
    }
}
