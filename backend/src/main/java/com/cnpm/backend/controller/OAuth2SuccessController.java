
package com.cnpm.backend.controller;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.servlet.view.RedirectView;

@Controller
public class OAuth2SuccessController {

    @Value("${app.frontend-url:http://localhost:3000}")
    private String frontendUrl;

    @GetMapping("/api/auth/oauth2/success")
    public RedirectView success() {
        return new RedirectView(frontendUrl + "/?oauth=success");
    }
}
