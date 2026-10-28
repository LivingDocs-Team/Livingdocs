package com.cnpm.backend.config;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;

import java.util.function.Supplier;

/** Uses masked tokens for rendered attributes and the cookie token for SPA headers. */
public final class SpaCsrfTokenRequestHandler implements CsrfTokenRequestHandler {

    public static final String RAW_TOKEN_ATTRIBUTE = SpaCsrfTokenRequestHandler.class.getName() + ".RAW_TOKEN";

    private final CsrfTokenRequestHandler xorHandler = new XorCsrfTokenRequestAttributeHandler();
    private final CsrfTokenRequestHandler plainHandler = new CsrfTokenRequestAttributeHandler();

    @Override
    public void handle(HttpServletRequest request, HttpServletResponse response,
            Supplier<CsrfToken> deferredCsrfToken) {
        xorHandler.handle(request, response, deferredCsrfToken);
        CsrfToken token = deferredCsrfToken.get();
        request.setAttribute(RAW_TOKEN_ATTRIBUTE, token.getToken());
    }

    @Override
    public String resolveCsrfTokenValue(HttpServletRequest request, CsrfToken csrfToken) {
        String header = request.getHeader(csrfToken.getHeaderName());
        return StringUtils.hasText(header)
                ? plainHandler.resolveCsrfTokenValue(request, csrfToken)
                : xorHandler.resolveCsrfTokenValue(request, csrfToken);
    }
}
