package com.livingdocs.github;

import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.service.DocumentationCollectionService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * Kiểm thử các tiêu chí chấp nhận của FR-COLLECTION (Docs/Nhân/FR11.md) mà
 * {@link DocumentationCollectionsPostgresTest} chưa bao phủ:
 * <ul>
 *   <li>AC-COLLECTION.4 / AC-COLLECTION.6: người phụ trách được lưu theo workspace,
 *       nên thấy giống nhau ở mọi collection chứa tài liệu và còn giữ khi gỡ tài liệu khỏi một collection.</li>
 *   <li>AC-COLLECTION.7: đổi repository chạy song song với gắn tài liệu từ repository cũ
 *       không để lại liên kết sai repository.</li>
 * </ul>
 * Chỉ chạy khi có PostgreSQL thật (biến COLLECTIONS_TEST_DB_URL), vì cần khóa hàng FOR UPDATE.
 * Mỗi test dùng workspace riêng để không ảnh hưởng dữ liệu của test khác trong cùng database.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@EnabledIfEnvironmentVariable(named = "COLLECTIONS_TEST_DB_URL", matches = ".+")
class DocumentationCollectionsAcceptancePostgresTest {
    private static final String LEAD = "ROLE_TECHNICAL_LEAD";
    private static final String DEVELOPER = "ROLE_DEVELOPER";
    private static final int RACE_ROUNDS = 20;

    @Autowired MockMvc mvc;
    @Autowired JdbcClient jdbc;
    @Autowired DocumentationCollectionService collections;

    @DynamicPropertySource
    static void postgres(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> System.getenv("COLLECTIONS_TEST_DB_URL"));
        registry.add("spring.datasource.username", () -> System.getenv("COLLECTIONS_TEST_DB_USER"));
        registry.add("spring.datasource.password", () -> System.getenv("COLLECTIONS_TEST_DB_PASSWORD"));
        registry.add("spring.datasource.driver-class-name", () -> "org.postgresql.Driver");
    }

    /** AC-COLLECTION.4 và AC-COLLECTION.6. */
    @Test
    void ownerAssignmentIsSharedByEveryCollectionInTheWorkspace() throws Exception {
        String workspace = "ws-ac-shared-" + UUID.randomUUID();
        String path = "/api/workspaces/" + workspace + "/collections";
        UUID repo = repository(workspace, 11);
        UUID document = document(repo);

        String first = path + "/" + create(workspace, "Shared A", repo);
        String second = path + "/" + create(workspace, "Shared B", repo);
        mvc.perform(as(put(first + "/documents/" + document), LEAD, workspace)).andExpect(status().isNoContent());
        mvc.perform(as(put(second + "/documents/" + document), LEAD, workspace)).andExpect(status().isNoContent());

        // Gán người phụ trách ở collection thứ nhất, đọc ở collection thứ hai.
        assignOwner(workspace, first, document, 73);
        expectOwner(workspace, second, document, "73");

        // Đổi người phụ trách ở collection thứ hai, collection thứ nhất thấy cùng giá trị.
        assignOwner(workspace, second, document, 74);
        expectOwner(workspace, first, document, "74");
        assertThat(assignmentCount(workspace, document)).isEqualTo(1);

        // Gỡ tài liệu khỏi collection thứ nhất: phân công vẫn còn ở collection thứ hai.
        mvc.perform(as(delete(first + "/documents/" + document), LEAD, workspace))
                .andExpect(status().isNoContent());
        mvc.perform(as(get(first + "/documents"), DEVELOPER, workspace)).andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(0));
        expectOwner(workspace, second, document, "74");

        // Không phân công được qua collection không còn chứa tài liệu.
        mvc.perform(as(put(first + "/documents/" + document + "/owner/75"), LEAD, workspace)
                .header("X-Verified-Document-Owner-Id", "75")).andExpect(status().isNotFound());
        expectOwner(workspace, second, document, "74");

        // Bỏ phân công ở collection còn chứa tài liệu thì không còn bản ghi phân công nào.
        mvc.perform(as(delete(second + "/documents/" + document + "/owner"), LEAD, workspace))
                .andExpect(status().isNoContent());
        mvc.perform(as(get(second + "/documents"), DEVELOPER, workspace)).andExpect(status().isOk())
                .andExpect(jsonPath("$[0].assignedOwnerId").isEmpty());
        assertThat(assignmentCount(workspace, document)).isZero();

        mvc.perform(as(delete(first), LEAD, workspace)).andExpect(status().isNoContent());
        mvc.perform(as(delete(second), LEAD, workspace)).andExpect(status().isNoContent());
    }

    /** AC-COLLECTION.7. */
    @Test
    void concurrentRepositoryChangeAndAttachNeverLeaveAForeignDocument() throws Exception {
        String workspace = "ws-ac-race-" + UUID.randomUUID();
        ExecutorService pool = Executors.newFixedThreadPool(2);
        int repositoryChanged = 0;
        int documentAttached = 0;
        try {
            for (int round = 0; round < RACE_ROUNDS; round++) {
                UUID oldRepo = repository(workspace, 1000L + 2L * round);
                UUID newRepo = repository(workspace, 1001L + 2L * round);
                UUID document = document(oldRepo);
                String name = "Race " + round;
                UUID id = collections.save(workspace, null, name, null, oldRepo).id();

                CountDownLatch start = new CountDownLatch(1);
                Future<HttpStatus> change = pool.submit(attempt(start,
                        () -> collections.save(workspace, id, name, null, newRepo)));
                Future<HttpStatus> attach = pool.submit(attempt(start,
                        () -> collections.attach(workspace, id, document)));
                start.countDown();
                HttpStatus changeResult = change.get(30, TimeUnit.SECONDS);
                HttpStatus attachResult = attach.get(30, TimeUnit.SECONDS);

                UUID finalRepo = jdbc.sql("SELECT repository_id FROM documentation_collections WHERE id = ?")
                        .param(id).query(UUID.class).single();
                int members = jdbc.sql("SELECT count(*) FROM documentation_collection_documents WHERE collection_id = ?")
                        .param(id).query(Integer.class).single();
                String outcome = "round " + round + ": change=" + changeResult + ", attach=" + attachResult;

                // Không bao giờ có tài liệu thuộc repository khác với repository của collection.
                assertThat(foreignMembers(id)).as(outcome).isZero();
                if (newRepo.equals(finalRepo)) {
                    // Đổi repository chạy trước: gắn tài liệu từ repository cũ bị từ chối.
                    assertThat(changeResult).as(outcome).isEqualTo(HttpStatus.OK);
                    assertThat(attachResult).as(outcome).isEqualTo(HttpStatus.NOT_FOUND);
                    assertThat(members).as(outcome).isZero();
                    repositoryChanged++;
                } else {
                    // Gắn tài liệu chạy trước: đổi repository bị từ chối, collection giữ repository cũ.
                    assertThat(finalRepo).as(outcome).isEqualTo(oldRepo);
                    assertThat(attachResult).as(outcome).isEqualTo(HttpStatus.OK);
                    assertThat(changeResult).as(outcome).isEqualTo(HttpStatus.CONFLICT);
                    assertThat(members).as(outcome).isEqualTo(1);
                    documentAttached++;
                }
                collections.delete(workspace, id);
            }
        } finally {
            pool.shutdownNow();
        }
        assertThat(repositoryChanged + documentAttached).isEqualTo(RACE_ROUNDS);
    }

    private Callable<HttpStatus> attempt(CountDownLatch start, Runnable action) {
        return () -> {
            start.await();
            try {
                action.run();
                return HttpStatus.OK;
            } catch (ApiException exception) {
                return exception.getStatus();
            }
        };
    }

    private String create(String workspace, String name, UUID repository) throws Exception {
        mvc.perform(as(post("/api/workspaces/" + workspace + "/collections"), LEAD, workspace)
                        .contentType("application/json")
                        .content("""
                                {"name":"%s","repositoryId":"%s"}
                                """.formatted(name, repository)))
                .andExpect(status().isCreated());
        return jdbc.sql("SELECT id FROM documentation_collections WHERE workspace_id = ? AND name = ?")
                .params(workspace, name).query(UUID.class).single().toString();
    }

    private void assignOwner(String workspace, String collection, UUID document, long owner) throws Exception {
        mvc.perform(as(put(collection + "/documents/" + document + "/owner/" + owner), LEAD, workspace)
                .header("X-Verified-Document-Owner-Id", String.valueOf(owner))).andExpect(status().isNoContent());
    }

    private void expectOwner(String workspace, String collection, UUID document, String owner) throws Exception {
        mvc.perform(as(get(collection + "/documents"), DEVELOPER, workspace)).andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].id").value(document.toString()))
                .andExpect(jsonPath("$[0].assignedOwnerId").value(owner));
    }

    private int assignmentCount(String workspace, UUID document) {
        return jdbc.sql("""
                SELECT count(*) FROM documentation_owner_assignments WHERE workspace_id = ? AND document_id = ?
                """).params(workspace, document).query(Integer.class).single();
    }

    private int foreignMembers(UUID collection) {
        return jdbc.sql("""
                SELECT count(*) FROM documentation_collection_documents m
                JOIN documentation_collections c ON c.id = m.collection_id
                JOIN documentation_artifacts d ON d.id = m.document_id
                WHERE c.id = ? AND d.repository_id IS DISTINCT FROM c.repository_id
                """).param(collection).query(Integer.class).single();
    }

    private MockHttpServletRequestBuilder as(MockHttpServletRequestBuilder request, String role, String workspace) {
        return request.header("Authorization", "Bearer test-only-internal-credential")
                .header("X-User-Authorities", role)
                .header("X-Verified-Workspace-Id", workspace)
                .header("X-Verified-Workspace-Access", "MEMBER");
    }

    private UUID repository(String workspace, long githubId) {
        UUID repository = UUID.randomUUID();
        UUID connection = UUID.randomUUID();
        jdbc.sql("""
                INSERT INTO github_connections (id, user_id, github_user_id, github_login, status, created_at, updated_at)
                VALUES (?, ?, 1, 'test-user', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """).params(connection, connection.toString()).update();
        jdbc.sql("""
                INSERT INTO repositories (id, workspace_id, connection_id, github_repo_id, full_name, status, created_at)
                VALUES (?, ?, ?, ?, 'org/repo', 'CONNECTED', CURRENT_TIMESTAMP)
                """).params(repository, workspace, connection, githubId).update();
        return repository;
    }

    private UUID document(UUID repository) {
        UUID document = UUID.randomUUID();
        jdbc.sql("""
                INSERT INTO documentation_artifacts
                    (id, repository_id, owner_user_id, generation_job_id, markdown, created_at, updated_at)
                VALUES (?, ?, '73', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """).params(document, repository, document.toString(), "# Shared document\n\nBody").update();
        return document;
    }
}
