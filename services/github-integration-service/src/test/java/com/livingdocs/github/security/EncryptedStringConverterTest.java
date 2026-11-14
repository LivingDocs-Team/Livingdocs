package com.livingdocs.github.security;

import org.junit.jupiter.api.Test;

import java.util.Arrays;
import java.util.Base64;

import static org.assertj.core.api.Assertions.assertThat;

/** LD-76: token không giải mã được thì coi như không còn, không làm lỗi 500 cả API. */
class EncryptedStringConverterTest {

    private static final String KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";

    @Test
    void encryptThenDecrypt_returnsOriginal() {
        EncryptedStringConverter converter = converter(KEY);
        String stored = converter.convertToDatabaseColumn("ghu_secret_token");

        assertThat(stored).isNotEqualTo("ghu_secret_token");
        assertThat(converter.convertToEntityAttribute(stored)).isEqualTo("ghu_secret_token");
    }

    @Test
    void tokenEncryptedWithAnotherKey_isTreatedAsMissing() {
        byte[] otherKey = new byte[32];
        Arrays.fill(otherKey, (byte) 7);
        String stored = converter(Base64.getEncoder().encodeToString(otherKey))
                .convertToDatabaseColumn("ghu_secret_token");

        assertThat(converter(KEY).convertToEntityAttribute(stored)).isNull();
    }

    @Test
    void corruptedValue_isTreatedAsMissing() {
        EncryptedStringConverter converter = converter(KEY);

        assertThat(converter.convertToEntityAttribute("khong-phai-base64!")).isNull();
        assertThat(converter.convertToEntityAttribute("AAAA")).isNull(); // ngắn hơn IV 12 byte
    }

    @Test
    void nullStaysNull() {
        EncryptedStringConverter converter = converter(KEY);

        assertThat(converter.convertToDatabaseColumn(null)).isNull();
        assertThat(converter.convertToEntityAttribute(null)).isNull();
    }

    private static EncryptedStringConverter converter(String base64Key) {
        return new EncryptedStringConverter(new TokenEncryptor(base64Key));
    }
}



