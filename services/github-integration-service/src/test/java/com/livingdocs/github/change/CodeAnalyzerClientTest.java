package com.livingdocs.github.change;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class CodeAnalyzerClientTest {

    @Test
    void readsClassesMethodsFunctionsAndEndpointsWithLineRanges() throws Exception {
        // Dạng FileAnalysis của Code Analyzer (app/models.py), rút gọn
        String file = """
                {"path": "app/main.py", "status": "ok",
                 "classes": [{"name": "Shop", "kind": "class", "lineno": 3, "end_lineno": 9,
                              "methods": [{"name": "buy", "lineno": 4, "end_lineno": 6},
                                          {"name": "unknownRange", "lineno": 7}]},
                             {"name": "Status", "kind": "enum", "lineno": 11, "end_lineno": 13, "methods": []}],
                 "functions": [{"name": "items", "lineno": 16, "end_lineno": 17}],
                 "endpoints": [{"http_method": "GET", "path": "/items", "lineno": 16, "end_lineno": 17}]}
                """;

        assertThat(CodeAnalyzerClient.entities(new ObjectMapper().readTree(file))).containsExactly(
                new CodeEntity("CLASS", "Shop", 3, 9),
                new CodeEntity("METHOD", "Shop.buy", 4, 6),
                new CodeEntity("ENUM", "Status", 11, 13),
                new CodeEntity("FUNCTION", "items", 16, 17),
                new CodeEntity("ENDPOINT", "GET /items", 16, 17));
    }
}
