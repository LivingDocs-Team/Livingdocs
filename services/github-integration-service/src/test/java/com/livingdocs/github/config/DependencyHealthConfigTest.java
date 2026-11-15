package com.livingdocs.github.config;

import java.io.IOException;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.boot.actuate.health.Status;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.test.web.client.ResponseCreator;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class DependencyHealthConfigTest {
    @ParameterizedTest
    @ValueSource(strings = {"ai", "analyzer"})
    void reportsHealthFromTheConfiguredDependency(String dependency) {
        check(dependency, withSuccess("{\"status\":\"ok\"}", MediaType.APPLICATION_JSON), Status.UP);
        check(dependency, withSuccess("{\"status\":\"down\"}", MediaType.APPLICATION_JSON), Status.DOWN);
        check(dependency, withServerError(), Status.DOWN);
        check(dependency, withException(new IOException("Connection refused")), Status.DOWN);
    }

    private void check(String dependency, ResponseCreator response, Status expected) {
        String baseUrl = "http://" + dependency + ".test";
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        server.expect(requestTo(baseUrl + "/health")).andRespond(response);
        var indicator = DependencyHealthConfig.probe(builder.baseUrl(baseUrl).build());

        assertThat(indicator.health().getStatus()).isEqualTo(expected);
        server.verify();
    }
}
