package com.livingdocs.github.entity;

public enum ConnectionStatus {
    /** Đang kết nối bình thường. */
    ACTIVE,
    /** Token không còn dùng được (hết hạn, bị thu hồi phía GitHub) - cần kết nối lại. */
    INVALID,
    /** Người dùng đã chủ động ngắt kết nối. */
    REVOKED
}
