# LivingDocs — Đặc tả chức năng LD-405: Verify Code–Documentation Migration

## 1. Mục tiêu

LD-405 tập trung xác minh việc tích hợp migration cơ sở dữ liệu cho chức năng liên kết giữa tài liệu và các thực thể mã nguồn (Code–Documentation Relationship), vốn được triển khai trong PR #102.

Mục tiêu chính là bảo đảm migration có thể chạy trên cả database mới và database đã tồn tại, không làm mất dữ liệu hoặc phá vỡ lịch sử migration đã áp dụng. Đồng thời, các ràng buộc dữ liệu của quan hệ tài liệu–code phải được giữ nguyên và API quản lý quan hệ vẫn hoạt động sau khi schema được nâng cấp.

Trong snapshot code được cung cấp, phạm vi LD-405 được thể hiện qua ba nhóm:

1. **Migration và lựa chọn migration lineage:** xử lý sự trùng lặp version migration giữa các nhánh tính năng, nhận diện đúng lịch sử Flyway hiện có và chọn bộ migration tương thích.
2. **Bảo toàn schema và dữ liệu:** kiểm tra database mới, nâng cấp database cũ, giữ nguyên checksum/lịch sử đã áp dụng, đồng thời xác minh khóa ngoại, unique constraint và cascade delete.
3. **Xác minh API quan hệ:** kiểm tra API đọc/ghi liên kết tài liệu với code entity, quyền sở hữu repository, xử lý entity bị xóa/khôi phục và tính ổn định của ID khi vị trí dòng code thay đổi.

Đây là chức năng kiểm tra và bảo đảm tính tương thích của migration; không phải một giao diện người dùng độc lập.

## 2. Thành phần và vị trí mã nguồn

### 2.1. Migration và cấu hình Flyway

Các thành phần chính nằm trong `services/github-integration-service`:

- `src/main/resources/db/migration/`: các migration gốc, bao gồm `V5__documentation_code_relationships.sql` và các migration liên quan.
- `src/main/resources/db/migration-current/`: lineage hiện tại, có migration kết hợp `V5__documentation_code_relationships_and_pull_requests.sql`.
- `src/main/resources/db/migration-current-documents-v5/`: lineage dành cho database đã áp dụng migration tài liệu ở version 5.
- `src/main/resources/db/migration-current-pull-requests-v5/`: lineage dành cho database đã áp dụng migration Pull Request ở version 5.
- `src/main/resources/db/migration-current-documents-v5-source-changes-v6/`: lineage đã có Documentation V5 và Source Changes V6.
- `src/main/resources/db/migration-current-pull-requests-v5-source-changes-v6/`: lineage đã có Pull Requests V5 và Source Changes V6.
- `src/main/resources/db/migration-legacy/`: lineage cũ có quan hệ tài liệu–code từ V2.
- `src/main/resources/db/migration-common/`: các migration dùng chung, gồm V8 affected documents và V9 system analytics indexes.
- `config/FlywayMigrationLineageSelector.java`: đọc lịch sử Flyway và chọn lineage tương ứng.
- `config/FlywayMigrationLineageConfig.java`: cấu hình Flyway sử dụng lineage đã chọn cùng `classpath:db/migration-common`.

### 2.2. Các thành phần quản lý quan hệ tài liệu–code

| Thành phần | Vị trí |
|---|---|
| Controller | `controller/DocumentationCodeRelationshipController.java` |
| Service | `service/DocumentationCodeRelationshipService.java` |
| Entity quan hệ | `entity/DocumentationCodeRelationship.java` |
| Repository quan hệ | `repository/DocumentationCodeRelationshipRepository.java` |
| Entity tài liệu | `entity/DocumentationArtifact.java` |
| Entity code | `entity/CodeEntity.java` |
| DTO phản hồi | `dto/DocumentationArtifactResponse.java`, `dto/CodeEntityResponse.java` |
| DTO cập nhật liên kết | `dto/ReplaceDocumentationCodeLinksRequest.java` |
| Hợp đồng API | `docs/documentation-code-relationship-contract.md` |

### 2.3. Kiểm thử và CI

- `src/test/java/com/livingdocs/github/DocumentationCodeRelationshipMigrationTest.java`: kiểm tra migration database mới và nâng cấp database cũ.
- `src/test/java/com/livingdocs/github/config/FlywayMigrationLineageSelectorTest.java`: kiểm tra lựa chọn lineage theo lịch sử Flyway, checksum và các trường hợp lịch sử không hợp lệ.
- `src/test/java/com/livingdocs/github/DocumentationCodeRelationshipApiTest.java`: kiểm tra API quan hệ trên Spring Boot test context.
- `.github/workflows/ci.yml`: job `github-integration-test` chạy Maven verify, kiểm tra API quan hệ với PostgreSQL và chạy các kiểm thử GitHub Integration khác.

## 3. Tổng quan dữ liệu và kiến trúc

Chức năng quan hệ tài liệu–code thuộc GitHub Integration Service, sử dụng PostgreSQL và Flyway. Backend đóng vai trò BFF chuyển tiếp request từ trình duyệt đến GitHub Integration Service; API quan hệ nhận `X-User-Id` đã được Backend chuyển tiếp.

### 3.1. Các bảng chính do migration quan hệ tạo ra

| Bảng | Mục đích |
|---|---|
| `documentation_artifacts` | Lưu bản ghi tài liệu được sinh cho repository, chủ sở hữu, generation job, Markdown và commit nguồn |
| `code_entities` | Lưu các class, method, function, endpoint được trích xuất từ kết quả phân tích code |
| `documentation_code_relationships` | Lưu liên kết giữa một tài liệu và một code entity |

Migration V5 kết hợp trong lineage hiện tại còn tạo các bảng cho hoạt động GitHub Pull Request/commit:

- `github_webhook_deliveries`
- `github_commits`
- `github_pull_requests`

Các bảng này thuộc phần migration Pull Request đi kèm trong cùng lineage; chúng không phải bảng quan hệ tài liệu–code cốt lõi.

### 3.2. Ràng buộc dữ liệu

Các ràng buộc quan trọng trong schema quan hệ:

- `documentation_artifacts.id`, `code_entities.id` và `documentation_code_relationships.id` là khóa chính UUID.
- `documentation_artifacts.repository_id` tham chiếu `repositories(id)` với `ON DELETE CASCADE`.
- `code_entities.repository_id` tham chiếu `repositories(id)` với `ON DELETE CASCADE`.
- `documentation_code_relationships.documentation_id` tham chiếu `documentation_artifacts(id)` với `ON DELETE CASCADE`.
- `documentation_code_relationships.code_entity_id` tham chiếu `code_entities(id)` với `ON DELETE CASCADE`.
- `documentation_artifacts.generation_job_id` có unique constraint.
- `code_entities` có unique constraint trên cặp `(repository_id, stable_key)`.
- `documentation_code_relationships` có unique constraint trên cặp `(documentation_id, code_entity_id)`.

Các index phục vụ truy vấn gồm index tài liệu theo repository/thời điểm tạo, index code entity theo repository/trạng thái/path và index quan hệ theo `code_entity_id`.

Nhờ các ràng buộc trên, một tài liệu không thể liên kết lặp với cùng một code entity; một stable key không bị nhân đôi trong cùng repository. Khi repository bị xóa, tài liệu, code entity và quan hệ phụ thuộc được xóa theo cascade.

### 3.3. Vòng đời code entity

Code entity được tạo/cập nhật từ kết quả phân tích repository và snapshot nguồn:

- Loại entity được ghi nhận gồm `class`, `method`, `function` và `endpoint`.
- `stable_key` được tạo bằng SHA-256 từ đường dẫn file, loại entity và tên định danh (qualified name); line number không tham gia khóa định danh.
- `line_start`, `line_end`, `source_commit` và `source_url` được cập nhật theo snapshot mới.
- Entity không còn xuất hiện trong kết quả phân tích phù hợp được đánh dấu `active = false`; các liên kết cũ không bị xóa.
- Khi entity xuất hiện lại với cùng stable key, bản ghi cũ được kích hoạt lại, giúp giữ nguyên ID và các liên kết đã lưu.
- Entity inactive không xuất hiện trong kết quả API quan hệ.

Việc đánh dấu inactive toàn bộ entity của các file không còn trong snapshot chỉ được thực hiện khi snapshot không bị giới hạn bởi `treeTruncated` hoặc `fileLimitReached`.

## 4. Xử lý xung đột migration và lựa chọn lineage

### 4.1. Bối cảnh xung đột

Đề bài LD-405 yêu cầu xác minh migration code–documentation từ PR #102. Trong repository, nhiều nhánh tính năng đã sử dụng chung version migration V5 cho các nội dung khác nhau, điển hình:

- `V5__documentation_code_relationships.sql`
- `V5__pull_requests_and_commits.sql`

Nếu Flyway cùng nhìn thấy hai migration có cùng version, service có thể không khởi động được do trùng version. Ngoài ra, một số database đã áp dụng V5 hoặc V6 theo thứ tự khác nhau. Vì vậy, chỉ đổi tên migration trong một thư mục duy nhất hoặc chạy một bộ migration cố định có thể làm checksum/lịch sử database cũ không còn khớp.

Snapshot code giải quyết vấn đề bằng cách giữ các lineage migration riêng và chọn lineage dựa trên lịch sử thực tế của database.

### 4.2. Cơ chế FlywayMigrationLineageSelector

`FlywayMigrationLineageSelector.select(DataSource)` đọc metadata database và bảng `flyway_schema_history` trước khi Flyway thực hiện migration.

Các nguyên tắc kiểm tra:

1. Database trống, chưa có bảng ứng dụng và chưa có Flyway history: chọn lineage `CURRENT`.
2. Có bảng ứng dụng nhưng không có Flyway history: từ chối chọn lineage.
3. Flyway history rỗng nhưng đã có bảng ứng dụng: từ chối chọn lineage.
4. Có migration thất bại: từ chối chọn lineage.
5. Phải có migration V1 đúng tên `V1__init_github_integration.sql`.
6. Với V2, selector phân biệt lịch sử legacy và current bằng cả tên script lẫn checksum.
7. Với các version V5/V6, selector kiểm tra tên script để xác định migration nào đã được áp dụng và chọn bộ migration tiếp nối tương thích.
8. Nếu script/checksum hoặc chuỗi migration không nằm trong các trường hợp đã hỗ trợ, selector dừng và không bỏ qua validation.

Hai checksum V2 được dùng để nhận diện lineage:

- Legacy: `V2__documentation_code_relationships.sql`.
- Current: `V2__document_review_workflow.sql`.

Selector không tự ý sửa Flyway history, không xóa migration cũ và không dùng `repair` để ép database khớp với một lineage không xác định.

### 4.3. Các lineage được hỗ trợ

| Lineage | Trường hợp sử dụng |
|---|---|
| `CURRENT` | Database mới hoặc database theo lịch sử current, sử dụng V5 kết hợp tài liệu và Pull Request |
| `LEGACY_RELATIONSHIPS_V2` | Database đã áp dụng migration quan hệ tài liệu–code từ V2 legacy |
| `CURRENT_DOCUMENTATION_V5` | Database current đã áp dụng Documentation V5 trước |
| `CURRENT_PULL_REQUESTS_V5` | Database current đã áp dụng Pull Requests V5 trước |
| `CURRENT_DOCUMENTATION_V5_SOURCE_CHANGES_V6` | Database đã có Documentation V5 và Source Changes V6 |
| `CURRENT_PULL_REQUESTS_V5_SOURCE_CHANGES_V6` | Database đã có Pull Requests V5 và Source Changes V6 |

Với database mới, `CURRENT` sử dụng migration V5 kết hợp:

`V5__documentation_code_relationships_and_pull_requests.sql`

Với database đã áp dụng một nhánh V5 riêng, các lineage tương ứng giữ nguyên migration đã chạy và đưa phần tính năng còn thiếu vào version tiếp theo (V6 hoặc V7 tùy lịch sử V5/V6). Với database đã có Source Changes V6, selector dùng lineage riêng để thêm phần còn thiếu ở V7 mà không thay đổi checksum V6 đã áp dụng.

### 4.4. Cấu hình migration khi service khởi động

`FlywayMigrationLineageConfig` đăng ký `FlywayConfigurationCustomizer`. Khi Flyway được cấu hình, customizer gọi selector để lấy location phù hợp và bổ sung location dùng chung:

```java
configuration.locations(
    selector.select(dataSource).location(),
    "classpath:db/migration-common"
);
```

Do đó, Flyway sử dụng đúng một lineage chính cho database hiện tại, đồng thời vẫn chạy các migration chung.

## 5. Migration schema quan hệ tài liệu–code

### 5.1. Bảng `documentation_artifacts`

Lưu bản ghi tài liệu sinh ra từ một generation job, gắn với repository và user sở hữu. Các trường chính gồm:

- `id`: UUID tài liệu.
- `repository_id`: repository nguồn.
- `owner_user_id`: user sở hữu tài liệu.
- `generation_job_id`: mã job sinh tài liệu, duy nhất.
- `markdown`: nội dung Markdown.
- `source_commit`: commit nguồn.
- `created_at`, `updated_at`: thời điểm tạo/cập nhật.

### 5.2. Bảng `code_entities`

Lưu các thực thể được phân tích từ repository:

- `id`: UUID code entity.
- `repository_id`: repository chứa entity.
- `stable_key`: khóa ổn định theo path + type + name.
- `entity_type`, `name`: loại và tên entity.
- `path`: đường dẫn file.
- `line_start`, `line_end`: vị trí trong source file.
- `source_url`: liên kết GitHub đến source và vùng dòng tương ứng.
- `source_commit`: commit dùng để tạo liên kết.
- `active`: trạng thái entity.
- `last_seen_at`: thời điểm entity được nhìn thấy gần nhất.

### 5.3. Bảng `documentation_code_relationships`

Bảng nối hai chiều giữa tài liệu và code entity:

- `id`: UUID quan hệ.
- `documentation_id`: tài liệu được liên kết.
- `code_entity_id`: code entity được liên kết.
- `created_at`: thời điểm tạo quan hệ.

Unique constraint `(documentation_id, code_entity_id)` ngăn tạo quan hệ trùng lặp. Hai khóa ngoại cascade bảo đảm quan hệ không tồn tại độc lập khi tài liệu hoặc code entity bị xóa.

## 6. Chức năng API liên quan

Tất cả endpoint dưới đây yêu cầu `X-User-Id` được Backend chuyển tiếp sau xác thực. Service kiểm tra quyền sở hữu repository/tài liệu trước khi trả hoặc cập nhật dữ liệu.

| Method | Endpoint | Chức năng |
|---|---|---|
| `GET` | `/api/repositories/{repositoryId}/code-entities` | Liệt kê code entity đang active của repository |
| `GET` | `/api/repositories/{repositoryId}/documentation` | Liệt kê tài liệu của repository |
| `GET` | `/api/documentation/{documentId}` | Lấy thông tin tài liệu |
| `GET` | `/api/documentation/{documentId}/code-entities` | Lấy các code entity được liên kết với tài liệu |
| `PUT` | `/api/documentation/{documentId}/code-entities` | Thay thế danh sách code entity liên kết với tài liệu |
| `GET` | `/api/documentation/code-entities/{entityId}/documents` | Lấy các tài liệu liên kết với code entity |

### 6.1. Tạo và cập nhật dữ liệu khi sinh tài liệu

`DocumentationCodeRelationshipService.recordGeneration(...)`:

1. Xác minh user sở hữu repository.
2. Tạo hoặc cập nhật `DocumentationArtifact` theo generation job ID.
3. Ghi nhận source commit từ snapshot.
4. Đọc kết quả phân tích `files`.
5. Tạo/cập nhật entity class, method, function và endpoint.
6. Tính stable key để nhận diện entity qua các lần phân tích.
7. Cập nhật source URL và line range theo snapshot hiện tại.
8. Đánh dấu entity không còn tồn tại là inactive trong điều kiện snapshot đầy đủ.

`saveGeneratedMarkdown(...)` lưu nội dung Markdown cho tài liệu thuộc đúng user và generation job.

### 6.2. Thay thế danh sách liên kết

Request `PUT /api/documentation/{documentId}/code-entities` nhận body có trường `codeEntityIds`.

Quy tắc xử lý:

- Loại bỏ ID trùng lặp bằng tập hợp có thứ tự.
- Chỉ chấp nhận entity đang active và thuộc cùng repository với tài liệu.
- Nếu có ID không tồn tại, inactive hoặc thuộc repository khác, trả lỗi `400` và không xóa các liên kết hiện tại.
- Khi request hợp lệ, xóa danh sách liên kết cũ rồi tạo lại theo danh sách mới.
- Danh sách rỗng có nghĩa là xóa toàn bộ liên kết của tài liệu.

### 6.3. Đọc quan hệ hai chiều

- Từ tài liệu có thể truy vấn các code entity đang active được liên kết.
- Từ code entity có thể truy vấn các tài liệu thuộc cùng user và repository.
- Entity inactive bị ẩn khỏi kết quả, nhưng quan hệ đã lưu vẫn còn để có thể xuất hiện lại nếu entity được khôi phục.

## 7. Kiểm tra database mới và database hiện có

### 7.1. Database mới (Fresh database)

`DocumentationCodeRelationshipMigrationTest.freshDatabaseMigrationPassesAllVersionsAndValidatesJpaSchema()`:

1. Tạo H2 database độc lập ở chế độ tương thích PostgreSQL.
2. Chạy Flyway trên `db/migration-current` và `db/migration-common`.
3. Xác nhận số migration đã chạy đạt ít nhất 5 và target schema version ít nhất 5.
4. Khởi tạo JPA EntityManagerFactory với `hibernate.hbm2ddl.auto=validate`.
5. Xác nhận schema được tạo bởi migration tương thích với mapping entity JPA.

Bước validate không yêu cầu Hibernate tự tạo schema; Hibernate chỉ đối chiếu mapping với schema đã được Flyway tạo.

### 7.2. Database cũ đang ở V4

`existingDatabaseAtV4UpgradesCleanlyToV5WithoutDataLossAndEnforcesConstraints()`:

1. Tạo database test và chạy migration đến target V4.
2. Chèn dữ liệu đã tồn tại gồm GitHub connection, repository, document workflow và audit record.
3. Chạy các migration còn lại để nâng cấp lên V5 trở lên.
4. Kiểm tra repository và audit record đã chèn vẫn còn.
5. Kiểm tra unique constraint của `generation_job_id`.
6. Kiểm tra unique constraint của `(repository_id, stable_key)`.
7. Kiểm tra unique constraint của `(documentation_id, code_entity_id)`.
8. Xóa repository và xác nhận các bảng tài liệu, code entity, quan hệ phụ thuộc được xóa theo cascade.

### 7.3. Database có lịch sử V5/V6 khác nhau

`FlywayMigrationLineageSelectorTest` tạo các database H2 mô phỏng những lịch sử migration khác nhau:

- Database trống chọn `CURRENT`.
- Database legacy có V2 quan hệ và checksum đúng chọn `LEGACY_RELATIONSHIPS_V2`.
- Database current có V2 workflow và checksum đúng chọn `CURRENT`.
- Database đã chạy Documentation V5 hoặc Pull Requests V5 được chọn lineage tương ứng.
- Database đã chạy V5 và Source Changes V6 giữ nguyên checksum V6, sau đó chạy migration còn thiếu ở V7.
- Database legacy giữ nguyên checksum V2 và dữ liệu quan hệ đã có khi nâng cấp tiếp.
- Checksum V2 không nhận diện được, thiếu bảng quan hệ legacy, có migration thất bại hoặc có bảng ứng dụng mà không có Flyway history đều bị từ chối.

Các test này nhằm xác nhận selector không chọn nhầm migration và không làm thay đổi lịch sử đã áp dụng.

## 8. Kiểm thử API quan hệ

`DocumentationCodeRelationshipApiTest` chạy Spring Boot test context với MockMvc, H2 và các thành phần GitHub/repository sync được mock phù hợp.

Các tình huống được kiểm tra:

1. Sinh tài liệu từ dữ liệu phân tích và snapshot, sau đó truy vấn code entity của repository.
2. Xác nhận `sourceUrl` chứa commit và line range tương ứng.
3. Gửi danh sách entity ID có phần tử trùng lặp; API chỉ tạo liên kết duy nhất.
4. Đọc quan hệ từ tài liệu sang code entity.
5. Đọc quan hệ ngược từ code entity sang tài liệu.
6. Từ chối entity không tồn tại hoặc thuộc repository khác.
7. Khi request liên kết không hợp lệ, các liên kết hợp lệ đã tồn tại không bị xóa.
8. User khác không thể đọc tài liệu không thuộc quyền sở hữu.
9. Khi entity đổi line number nhưng giữ path/type/name, ID quan hệ vẫn được giữ; source URL và line range được cập nhật.
10. Khi entity biến mất khỏi phân tích, entity chuyển inactive và không còn hiển thị trong kết quả; khi entity xuất hiện lại, ID cũ và liên kết cũ được khôi phục.

## 9. Tích hợp CI

Trong `.github/workflows/ci.yml`, job liên quan là `github-integration-test` (tên hiển thị: **GitHub Integration Service Test**).

Job thực hiện:

### 9.1. Kiểm thử Maven

Chạy:

```bash
mvn --batch-mode --no-transfer-progress \
  -f services/github-integration-service/pom.xml verify
```

Đây là bước build và chạy bộ test của GitHub Integration Service, trong đó có các test migration, lineage selector và API quan hệ.

### 9.2. Kiểm tra API với PostgreSQL

CI khởi tạo PostgreSQL 16 với database `github_integration`, sau đó chạy riêng:

```bash
mvn --batch-mode --no-transfer-progress \
  -f services/github-integration-service/pom.xml test \
  -Dtest=DocumentationCodeRelationshipApiTest \
  -Dspring.datasource.url="$DB_URL" \
  -Dspring.datasource.username="$DB_USERNAME" \
  -Dspring.datasource.password="$DB_PASSWORD" \
  -Dspring.datasource.driver-class-name=org.postgresql.Driver \
  -Dspring.jpa.hibernate.ddl-auto=validate
```

Bước này kiểm tra API quan hệ trên PostgreSQL thực tế của CI và yêu cầu Hibernate validate schema thay vì tự tạo schema.

Các biến môi trường kiểm thử được khai báo trong workflow để khởi tạo service test; đây không phải giá trị secret dùng cho môi trường production.

### 9.3. Các bước CI khác trong cùng job

Sau bước PostgreSQL, job còn chạy `GitHubRepositoryFetcherLiveTest` với GitHub API và upload Surefire test reports. Các bước này thuộc pipeline GitHub Integration chung, không phải riêng logic migration LD-405.

## 10. Cách chạy kiểm thử thủ công

Từ thư mục gốc repository:

### 10.1. Chạy toàn bộ kiểm thử GitHub Integration Service

```bash
mvn --batch-mode --no-transfer-progress \
  -f services/github-integration-service/pom.xml verify
```

### 10.2. Chạy riêng test migration và ràng buộc schema

```bash
mvn --batch-mode --no-transfer-progress \
  -f services/github-integration-service/pom.xml test \
  -Dtest=DocumentationCodeRelationshipMigrationTest
```

### 10.3. Chạy riêng test lựa chọn migration lineage

```bash
mvn --batch-mode --no-transfer-progress \
  -f services/github-integration-service/pom.xml test \
  -Dtest=FlywayMigrationLineageSelectorTest
```

### 10.4. Chạy riêng test API quan hệ

```bash
mvn --batch-mode --no-transfer-progress \
  -f services/github-integration-service/pom.xml test \
  -Dtest=DocumentationCodeRelationshipApiTest
```

Các lệnh trên mô tả cách chạy test được khai báo trong repository. Không kết luận test đã pass chỉ từ việc có test source hoặc workflow; cần thực thi lệnh hoặc xem CI run tương ứng để xác nhận kết quả thực tế.

## 11. Tiêu chí chấp nhận

Đối chiếu với đề bài LD-405, các tiêu chí cần xác minh gồm:

1. **Fresh database migration:** database mới chạy được migration và schema tương thích với entity JPA.
2. **Existing database migration:** database đã có dữ liệu và migration cũ nâng cấp được mà không mất dữ liệu hiện có.
3. **Migration lineage compatibility:** database đã áp dụng các nhánh V5/V6 khác nhau được chọn đúng lineage; checksum và lịch sử đã áp dụng được bảo toàn.
4. **Constraints intact:** khóa ngoại, unique constraint và cascade delete của tài liệu, code entity và quan hệ hoạt động đúng.
5. **Relationship API integration:** API đọc/ghi liên kết tài liệu–code hoạt động, có kiểm tra quyền sở hữu và từ chối tham chiếu không hợp lệ.
6. **CI integration:** workflow có bước Maven verify và bước kiểm tra API quan hệ trên PostgreSQL.

## 12. Giới hạn và lưu ý vận hành

- Selector chỉ hỗ trợ các migration lineage và checksum được khai báo trong `FlywayMigrationLineageSelector`. Một lịch sử khác dự kiến phải được phân tích và bổ sung test trước khi được hỗ trợ.
- Nếu database có migration thất bại, thiếu Flyway history nhưng lại có bảng ứng dụng, hoặc checksum không nhận diện được, selector chủ động dừng. Không tự ý xóa database, chỉnh `flyway_schema_history`, chạy `repair` hay bỏ qua validation để làm service khởi động.
- Các thư mục migration-current* là những bộ migration thay thế nhau theo lịch sử database; không gộp tất cả location vào cùng một lần chạy nếu không có selector.
- Migration cũ đã được áp dụng cần giữ nguyên nội dung/checksum. Nếu cần thay đổi schema sau khi migration đã chạy trên môi trường dùng chung, hãy thêm migration mới theo lineage được hỗ trợ thay vì sửa migration cũ.
- Test H2 chạy ở chế độ PostgreSQL giúp kiểm tra phần lớn hành vi migration trong bộ test; CI bổ sung kiểm tra API quan hệ trên PostgreSQL 16. Không nên suy rộng test H2 thành bằng chứng rằng mọi biến thể PostgreSQL production đã được kiểm tra.
- API quan hệ yêu cầu danh tính user do Backend chuyển tiếp; không dùng `X-User-Id` do trình duyệt tự khai báo làm bằng chứng xác thực.
- Các test source có trong snapshot không tự chứng minh CI đã chạy thành công. Cần đối chiếu kết quả thực tế của workflow nếu cần xác nhận trạng thái pass.

## 13. Kết luận

LD-405 củng cố khả năng triển khai an toàn chức năng liên kết tài liệu với code entity trong bối cảnh repository có nhiều nhánh migration dùng chung version V5. Thay vì áp dụng một bộ migration duy nhất cho mọi database, hệ thống kiểm tra Flyway history, script và checksum để chọn lineage tương thích.

Bộ kiểm thử đi kèm xác minh database mới, nâng cấp database từ V4, bảo toàn dữ liệu và checksum của các lịch sử V5/V6, kiểm tra ràng buộc quan hệ và xác minh API trên Spring Boot. CI còn có bước chạy API test với PostgreSQL 16. Các nội dung này đáp ứng đúng trọng tâm đề bài: migration fresh/existing database, bảo toàn constraints/relationships, tích hợp API và CI.
