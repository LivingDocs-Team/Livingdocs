package com.livingdocs.github.security;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Tự động mã hoá khi lưu và giải mã khi đọc các cột token.
 * Dùng bằng cách gắn @Convert(converter = EncryptedStringConverter.class) lên field.
 */
@Component
@Converter
public class EncryptedStringConverter implements AttributeConverter<String, String> {

    private static final Logger log = LoggerFactory.getLogger(EncryptedStringConverter.class);

    private final TokenEncryptor encryptor;

    public EncryptedStringConverter(TokenEncryptor encryptor) {
        this.encryptor = encryptor;
    }

    @Override
    public String convertToDatabaseColumn(String attribute) {
        return encryptor.encrypt(attribute);
    }

    /**
     * Token không giải mã được (mã hoá bằng TOKEN_ENCRYPTION_KEY khác, hoặc dữ liệu hỏng) được coi như không còn:
     * kết nối sẽ báo INVALID để người dùng kết nối lại GitHub, thay vì mọi API GitHub trả lỗi 500 (LD-76).
     */
    @Override
    public String convertToEntityAttribute(String dbData) {
        try {
            return encryptor.decrypt(dbData);
        } catch (RuntimeException e) {
            log.warn("Cannot decrypt a stored GitHub token (was TOKEN_ENCRYPTION_KEY changed?). "
                    + "Treating it as missing: the user has to reconnect GitHub.");
            return null;
        }
    }
}
