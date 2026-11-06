
package com.cnpm.backend.controller;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.servlet.view.RedirectView;

@Controller
public class OAuth2SuccessController {

    @GetMapping("/api/auth/oauth2/success")
    public RedirectView success() {
        return new RedirectView("/?oauth=success");
    }
}
