package com.cnpm.backend.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.health.contributor.Status;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.test.web.client.ResponseCreator;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class IntegrationHealthConfigTest {
    @Test
    void usesIntegrationHealthStatus() {
        check(withSuccess("{\"status\":\"UP\"}", MediaType.APPLICATION_JSON), Status.UP);
        check(withSuccess("{\"status\":\"UNKNOWN\"}", MediaType.APPLICATION_JSON), Status.DOWN);
        check(withStatus(HttpStatus.SERVICE_UNAVAILABLE), Status.DOWN);
    }

    private void check(ResponseCreator response, Status expected) {
        var builder = RestClient.builder().baseUrl("http://integration.test");
        var server = MockRestServiceServer.bindTo(builder).build();
        server.expect(requestTo("http://integration.test/actuator/health")).andRespond(response);
        assertThat(IntegrationHealthConfig.probe(builder.build()).health().getStatus()).isEqualTo(expected);
        server.verify();
    }
}
