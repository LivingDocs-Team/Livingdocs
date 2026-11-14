package com.livingdocs.github.webhook;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.HexFormat;

/**
 * LD-69/LD-70: kiểm header X-Hub-Signature-256 của webhook GitHub.
 * GitHub ký nguyên body bằng HMAC-SHA256 với webhook secret và gửi "sha256=" + chữ ký dạng hex.
 */
public final class WebhookSignatureVerifier {

    private static final String PREFIX = "sha256=";

    private WebhookSignatureVerifier() {
    }

    public static boolean isValid(String secret, byte[] body, String signatureHeader) {
        if (secret == null || secret.isBlank() || body == null
                || signatureHeader == null || !signatureHeader.startsWith(PREFIX)) {
            return false;
        }
        byte[] supplied;
        try {
            supplied = HexFormat.of().parseHex(signatureHeader.substring(PREFIX.length()));
        } catch (IllegalArgumentException e) {
            return false;
        }
        return MessageDigest.isEqual(hmacSha256(secret, body), supplied);
    }

    static byte[] hmacSha256(String secret, byte[] body) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return mac.doFinal(body);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("HmacSHA256 is not available", e);
        }
    }
}



