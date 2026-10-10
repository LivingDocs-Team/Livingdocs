package com.livingdocs.github.security;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class TokenEncryptorTest {

    private static final String KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";

    @Test
    void encryptThenDecrypt_returnsOriginal() {
        TokenEncryptor encryptor = new TokenEncryptor(KEY);
        String cipher = encryptor.encrypt("ghu_secret_token");

        assertThat(cipher).isNotEqualTo("ghu_secret_token");
        assertThat(encryptor.decrypt(cipher)).isEqualTo("ghu_secret_token");
    }

    @Test
    void sameInput_producesDifferentCipherText() {
        TokenEncryptor encryptor = new TokenEncryptor(KEY);
        assertThat(encryptor.encrypt("abc")).isNotEqualTo(encryptor.encrypt("abc"));
    }

    @Test
    void nullStaysNull() {
        TokenEncryptor encryptor = new TokenEncryptor(KEY);
        assertThat(encryptor.encrypt(null)).isNull();
        assertThat(encryptor.decrypt(null)).isNull();
    }

    @Test
    void rejectsKeyWithWrongLength() {
        assertThatThrownBy(() -> new TokenEncryptor("AAAA"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("32 byte");
    }

    @Test
    void rejectsMissingKey() {
        assertThatThrownBy(() -> new TokenEncryptor(""))
                .isInstanceOf(IllegalStateException.class);
    }
}
