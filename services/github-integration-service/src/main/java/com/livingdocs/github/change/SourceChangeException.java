package com.livingdocs.github.change;

/** LD-116: lỗi khi phát hiện thay đổi; mã lỗi được lưu vào source change (trạng thái FAILED). */
public class SourceChangeException extends RuntimeException {

    private final String code;

    public SourceChangeException(String code, String message) {
        super(message);
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}



