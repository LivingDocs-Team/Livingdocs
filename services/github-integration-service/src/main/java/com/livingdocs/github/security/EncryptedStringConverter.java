package com.livingdocs.github.security;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;
import org.springframework.stereotype.Component;

/**
 * Tự động mã hoá khi lưu và giải mã khi đọc các cột token.
 * Dùng bằng cách gắn @Convert(converter = EncryptedStringConverter.class) lên field.
 */
@Component
@Converter
public class EncryptedStringConverter implements AttributeConverter<String, String> {

    private final TokenEncryptor encryptor;

    public EncryptedStringConverter(TokenEncryptor encryptor) {
        this.encryptor = encryptor;
    }

    @Override
    public String convertToDatabaseColumn(String attribute) {
        return encryptor.encrypt(attribute);
    }

    @Override
    public String convertToEntityAttribute(String dbData) {
        return encryptor.decrypt(dbData);
    }
}
