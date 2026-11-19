package com.livingdocs.github;

import com.fasterxml.jackson.databind.JsonNode;
import com.livingdocs.github.dto.DocumentationTemplateRequest;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.service.DocumentationTemplateService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.http.HttpMethod.DELETE;
import static org.springframework.http.HttpMethod.GET;
import static org.springframework.http.HttpMethod.POST;
import static org.springframework.http.HttpMethod.PUT;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class DocumentationTemplateServiceTest {

    private static final String TEMPLATE = """
            {"id":"a1b2c3d4","name":"Onboarding","description":"","instructions":"Short.",
             "sections":["Overview","Functions"],"built_in":false}
            """;

    private MockRestServiceServer aiServer;
    private DocumentationTemplateService service;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder();
        aiServer = MockRestServiceServer.bindTo(builder).build();
        service = new DocumentationTemplateService(builder.baseUrl("http://ai.test").build());
    }

    @Test
    void listsTemplatesFromAiService() {
        aiServer.expect(requestTo("http://ai.test/templates")).andExpect(method(GET))
                .andRespond(withSuccess("[" + TEMPLATE + "]", MediaType.APPLICATION_JSON));

        JsonNode templates = service.list();

        assertEquals(1, templates.size());
        assertEquals("Onboarding", templates.get(0).path("name").asText());
        aiServer.verify();
    }

    @Test
    void listsAllowedSections() {
        aiServer.expect(requestTo("http://ai.test/templates/sections")).andExpect(method(GET))
                .andRespond(withSuccess("""
                        {"sections":["Overview","Classes","Functions","API Endpoints"],"documents":{}}
                        """, MediaType.APPLICATION_JSON));

        assertEquals(4, service.sections().path("sections").size());
        aiServer.verify();
    }

    @Test
    void createsTemplateWithOnlyTheGivenFields() {
        aiServer.expect(requestTo("http://ai.test/templates")).andExpect(method(POST))
                .andExpect(content().json("""
                        {"name":"Onboarding","instructions":"Short.","sections":["Overview","Functions"]}
                        """, true))
                .andRespond(withStatus(HttpStatus.CREATED).contentType(MediaType.APPLICATION_JSON)
                        .body(TEMPLATE));

        JsonNode created = service.create(new DocumentationTemplateRequest(
                "Onboarding", null, "Short.", List.of("Overview", "Functions")));

        assertEquals("a1b2c3d4", created.path("id").asText());
        aiServer.verify();
    }

    @Test
    void updatesAndDeletesTemplate() {
        aiServer.expect(requestTo("http://ai.test/templates/a1b2c3d4")).andExpect(method(PUT))
                .andRespond(withSuccess(TEMPLATE, MediaType.APPLICATION_JSON));
        aiServer.expect(requestTo("http://ai.test/templates/a1b2c3d4")).andExpect(method(DELETE))
                .andRespond(withStatus(HttpStatus.NO_CONTENT));

        service.update("a1b2c3d4", new DocumentationTemplateRequest(
                "Onboarding", "", "Short.", List.of("Overview")));
        service.delete("a1b2c3d4");

        aiServer.verify();
    }

    @Test
    void mapsValidationErrorToBadRequestWithReadableReason() {
        aiServer.expect(requestTo("http://ai.test/templates")).andExpect(method(POST))
                .andRespond(withStatus(HttpStatus.UNPROCESSABLE_ENTITY)
                        .contentType(MediaType.APPLICATION_JSON).body("""
                                {"detail":[{"loc":["body","sections"],
                                  "msg":"Value error, unknown section 'Changelog'"}]}
                                """));

        ApiException error = assertThrows(ApiException.class, () -> service.create(
                new DocumentationTemplateRequest("X", "", "x", List.of("Changelog"))));

        assertEquals(HttpStatus.BAD_REQUEST, error.getStatus());
        assertEquals("TEMPLATE_INVALID", error.getCode());
        assertEquals("sections: Value error, unknown section 'Changelog'", error.getMessage());
    }

    @Test
    void mapsDuplicateNameReadOnlyAndMissingTemplate() {
        aiServer.expect(requestTo("http://ai.test/templates")).andRespond(
                withStatus(HttpStatus.CONFLICT).contentType(MediaType.APPLICATION_JSON)
                        .body("{\"detail\":\"A template named 'Onboarding' already exists\"}"));
        aiServer.expect(requestTo("http://ai.test/templates/default")).andRespond(
                withStatus(HttpStatus.FORBIDDEN).contentType(MediaType.APPLICATION_JSON)
                        .body("{\"detail\":\"Built-in templates cannot be deleted\"}"));
        aiServer.expect(requestTo("http://ai.test/templates/missing")).andRespond(
                withStatus(HttpStatus.NOT_FOUND));

        DocumentationTemplateRequest body =
                new DocumentationTemplateRequest("Onboarding", "", "x", List.of("Overview"));
        ApiException taken = assertThrows(ApiException.class, () -> service.create(body));
        ApiException readOnly = assertThrows(ApiException.class, () -> service.delete("default"));
        ApiException missing = assertThrows(ApiException.class, () -> service.get("missing"));

        assertEquals("TEMPLATE_NAME_TAKEN", taken.getCode());
        assertEquals("A template named 'Onboarding' already exists", taken.getMessage());
        assertEquals(HttpStatus.FORBIDDEN, readOnly.getStatus());
        assertEquals("TEMPLATE_READ_ONLY", readOnly.getCode());
        assertEquals(HttpStatus.NOT_FOUND, missing.getStatus());
        assertEquals("TEMPLATE_NOT_FOUND", missing.getCode());
    }

    @Test
    void mapsAiOutageToBadGatewayAndRejectsMissingBody() {
        aiServer.expect(requestTo("http://ai.test/templates")).andRespond(withServerError());

        ApiException outage = assertThrows(ApiException.class, () -> service.list());
        ApiException noBody = assertThrows(ApiException.class, () -> service.create(null));

        assertEquals(HttpStatus.BAD_GATEWAY, outage.getStatus());
        assertEquals("AI_SERVICE_FAILED", outage.getCode());
        assertEquals(HttpStatus.BAD_REQUEST, noBody.getStatus());
    }
}
