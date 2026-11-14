package com.acme.shop.web;

/** Order as returned by the API (Java 16 record). */
public record OrderDto(Long id, String code) {
    public String label() {
        return """
            Order %s
            """.formatted(code);
    }
}



