package com.livingdocs.github.dto;

/**
 * @param authorizeUrl link để người dùng đăng nhập GitHub và cho phép LivingDocs truy cập
 * @param installUrl   link để cài GitHub App vào tài khoản / organization và chọn repo
 * @param state        mã chống giả mạo, hết hạn sau 10 phút
 */
public record AuthorizeUrlResponse(String authorizeUrl, String installUrl, String state) {
}
