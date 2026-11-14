package com.livingdocs.github.webhook;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;

class WebhookSignatureVerifierTest {

    // Ví dụ trong tài liệu GitHub "Validating webhook deliveries"
    private static final String SECRET = "It's a Secret to Everybody";
    private static final byte[] BODY = "Hello, World!".getBytes(StandardCharsets.UTF_8);
    private static final String SIGNATURE =
            "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17";

    @Test
    void acceptsGitHubDocumentationExample() {
        assertThat(WebhookSignatureVerifier.isValid(SECRET, BODY, SIGNATURE)).isTrue();
    }

    @Test
    void rejectsChangedBodyOrOtherSecret() {
        assertThat(WebhookSignatureVerifier.isValid(SECRET, "Hello, World?".getBytes(StandardCharsets.UTF_8),
                SIGNATURE)).isFalse();
        assertThat(WebhookSignatureVerifier.isValid("another secret", BODY, SIGNATURE)).isFalse();
    }

    @Test
    void rejectsMissingOrMalformedHeaderAndBlankSecret() {
        assertThat(WebhookSignatureVerifier.isValid(SECRET, BODY, null)).isFalse();
        assertThat(WebhookSignatureVerifier.isValid(SECRET, BODY, "sha1=abc")).isFalse();
        assertThat(WebhookSignatureVerifier.isValid(SECRET, BODY, "sha256=not-hex")).isFalse();
        assertThat(WebhookSignatureVerifier.isValid(SECRET, BODY, SIGNATURE.substring(0, 20))).isFalse();
        assertThat(WebhookSignatureVerifier.isValid(" ", BODY, SIGNATURE)).isFalse();
    }
}



