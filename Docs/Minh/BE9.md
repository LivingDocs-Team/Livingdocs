# BE9—LD-405 & LD-211 Liên kết Tài liệu – Mã nguồn và Xác minh Migration

| Mục | Nội dung |
|---|---|
| Story Jira | LD-405 Verify Code–Documentation Migration (PR#102); LD-211 `[Code & Documentation Relationship] Implement Code & Documentation Relationship` |
| Task đã làm | LD-212 (Define Documentation-to-Code Relationships), LD-213 (Link Documentation to Source Code), LD-214 (Display Documentation-to-Code Relationships), LD-215 (Implement Document and Source Code Navigation), LD-216 (Test Documentation-to-Code Relationships); LD-405 (Sprint 7 — Migration Verification & Lineage Resolution) |
| Người thực hiện | Nguyễn Hữu Đăng Khôi (LD-211 / PR#102); tích hợp và xác minh migration trong LD-405 |
| Nhánh / PR & Trạng thái | Nhánh `LD-405` xác minh tích hợp **PR #102** (`LD-211`) và tương thích migration lineage |
| Thành phần | **GitHub Integration Service:** `controller/DocumentationCodeRelationshipController`, `service/DocumentationCodeRelationshipService`, `service/DocumentationGenerationService`, `entity/DocumentationArtifact`, `entity/CodeEntity`, `entity/DocumentationCodeRelationship`, `repository/*`, `dto/*`, `config/FlywayMigrationLineageSelector`, `config/FlywayMigrationLineageConfig`, `db/migration*/*.sql`, `docs/documentation-code-relationship-contract.md`<br>**Backend BFF:** `security/ApiRoutePermissions` (phân quyền route `/api/repositories/{id}/code-entities`, `/api/repositories/{id}/documentation`, `/api/documentation/**`) <br>**Frontend:** `frontend/src/DocumentationManagement.jsx`<br>**CI:** `.github/workflows/ci.yml` (`github-integration-test`) |
| Tác nhân | Người dùng LivingDocs (xem, gắn liên kết và điều hướng giữa tài liệu với mã nguồn), Backend BFF (xác thực và chuyển tiếp `X-User-Id`), GitHub Integration Service, GitHub Actions CI |

## 1. Mô tả

Tài liệu đặc tả chức năng quản lý **Quan hệ Tài liệu – Mã nguồn (Code–Documentation Relationship)** được xây dựng trong **LD-211 (PR#102)** cùng cơ chế **Xác minh và Tích hợp Migration Cơ sở dữ liệu** trong **LD-405**.

Phạm vi chức năng bao gồm hai phần bổ trợ chặt chẽ:
1. **Chức năng nghiệp vụ liên kết tài liệu – mã nguồn (LD-211: LD-212 – LD-216):** Định nghĩa mô hình dữ liệu lưu trữ tài liệu sinh ra (`documentation_artifacts`), thực thể mã nguồn trích xuất từ phân tích AST (`code_entities` gồm `class`, `method`, `function`, `endpoint`) và bảng liên kết hai chiều (`documentation_code_relationships`). Hệ thống cung cấp API và giao diện trên `DocumentationManagement.jsx` cho phép gắn/cập nhật liên kết giữa tài liệu với code entity, hiển thị danh sách thực thể liên quan và điều hướng hai chiều từ tài liệu tới đúng tệp/dòng mã nguồn trên GitHub (`#L<start>-L<end>`) cũng như tra cứu ngược từ code entity về các tài liệu liên kết.
2. **Xác minh migration và giải quyết xung đột lineage (LD-405):** Giải quyết xung đột trùng phiên bản migration `V5` giữa nhánh PR#102 (`V5__documentation_code_relationships.sql`) và nhánh Pull Request (`V5__pull_requests_and_commits.sql`) thông qua `FlywayMigrationLineageSelector`. Cơ chế này nhận diện lịch sử `flyway_schema_history` và checksum thực tế của database để chọn đúng lineage tương thích, bảo toàn dữ liệu hiện có, duy trì toàn vẹn khóa ngoại/unique constraint/cascade delete và kiểm chứng tích hợp API trên PostgreSQL trong CI.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-BE—09.1 | **(LD-212 — Định nghĩa mô hình dữ liệu)** Lưu trữ bản ghi tài liệu sinh ra trong bảng `documentation_artifacts` (`id`, `repository_id`, `owner_user_id`, `generation_job_id`, `markdown`, `source_commit`, `created_at`, `updated_at`), các thực thể mã nguồn trong `code_entities` (`id`, `repository_id`, `stable_key`, `entity_type`, `name`, `path`, `line_start`, `line_end`, `source_url`, `source_commit`, `active`, `last_seen_at`) và liên kết hai chiều trong `documentation_code_relationships` (`id`, `documentation_id`, `code_entity_id`, `created_at`). |
| FR-BE—09.2 | **(LD-212 — Định danh ổn định & vòng đời thực thể)** Tạo `stable_key` bằng mã băm SHA-256 của bộ `(path, entity_type, qualified_name)` (không phụ thuộc số dòng) để giữ nguyên `code_entities.id` và các liên kết cũ khi vị trí dòng code thay đổi. Khi thực thể biến mất khỏi lần phân tích mới (trên snapshot đầy đủ không bị `treeTruncated` hoặc `fileLimitReached`), đánh dấu `active = false` mà không xóa bản ghi quan hệ; khi thực thể xuất hiện lại với cùng `stable_key`, kích hoạt lại (`active = true`) và khôi phục liên kết cũ. |
| FR-BE—09.3 | **(LD-213 — Ghi nhận thực thể khi sinh tài liệu)** Khi sinh tài liệu (`DocumentationCodeRelationshipService.recordGeneration` và `saveGeneratedMarkdown`), tự động tạo/cập nhật `DocumentationArtifact` theo `generation_job_id`, trích xuất các `class`, `method` (định danh dạng `ClassName.methodName`), `function` và `endpoint` (`HTTP_METHOD /path`) từ kết quả phân tích hợp lệ (`status` là `ok` hoặc `empty`), đồng thời sinh `source_url` trỏ tới commit SHA và khoảng dòng `#L{lineStart}-L{lineEnd}` trên GitHub. |
| FR-BE—09.4 | **(LD-213 — Gắn và thay thế liên kết tài liệu – code)** Cung cấp `PUT /api/documentation/{documentId}/code-entities` nhận danh sách `codeEntityIds` (tối đa $500$ phần tử). Hệ thống khử trùng lặp ID theo thứ tự (`LinkedHashSet`), kiểm tra tất cả entity đều đang `active` và thuộc cùng `repository_id` với tài liệu; nếu hợp lệ thì thay thế toàn bộ liên kết cũ bằng danh sách mới (danh sách rỗng `[]` sẽ gỡ toàn bộ liên kết). |
| FR-BE—09.5 | **(LD-214 — Hiển thị danh sách tài liệu & thực thể liên kết)** Cung cấp các API đọc dữ liệu: `GET /api/repositories/{repositoryId}/code-entities` (liệt kê code entity đang active sắp xếp theo `path`, `lineStart`), `GET /api/repositories/{repositoryId}/documentation` (liệt kê tài liệu của user trong repository), `GET /api/documentation/{documentId}` (chi tiết tài liệu) và `GET /api/documentation/{documentId}/code-entities` (danh sách code entity đang active liên kết với tài liệu). |
| FR-BE—09.6 | **(LD-215 — Điều hướng hai chiều Tài liệu ↔ Mã nguồn)** Hỗ trợ điều hướng xuôi từ tài liệu sang mã nguồn qua trường `sourceUrl` (URL GitHub kèm commit SHA và anchor `#L<start>-L<end>`) của từng `CodeEntityResponse`, và điều hướng ngược từ một thực thể mã nguồn về các tài liệu liên quan qua `GET /api/documentation/code-entities/{entityId}/documents`. Giao diện `DocumentationManagement.jsx` hiển thị các liên kết này để người dùng mở trực tiếp mã nguồn hoặc chuyển đổi giữa tài liệu và thực thể code. |
| FR-BE—09.7 | **(Kiểm soát quyền truy cập & BFF)** Mọi endpoint quan hệ yêu cầu header `X-User-Id` đã được Backend BFF xác thực chuyển tiếp; service xác minh quyền sở hữu `repository` và `documentation_artifacts.owner_user_id` trước khi đọc/ghi, đồng thời `ApiRoutePermissions` trên Backend cấu hình quyền truy cập tuyến đường tương ứng. |
| FR-BE—09.8 | **(LD-405 — Toàn vẹn ràng buộc CSDL)** Áp dụng khóa chính UUID cho cả 3 bảng; khóa ngoại `ON DELETE CASCADE` từ `documentation_artifacts` và `code_entities` tới `repositories(id)`, và từ `documentation_code_relationships` tới `documentation_artifacts(id)` và `code_entities(id)`; ràng buộc `UNIQUE` trên `documentation_artifacts(generation_job_id)`, `code_entities(repository_id, stable_key)` và `documentation_code_relationships(documentation_id, code_entity_id)`. |
| FR-BE—09.9 | **(LD-405 — Nhận diện Flyway Migration Lineage)** Trước khi Flyway chạy migration, `FlywayMigrationLineageSelector.select(DataSource)` kiểm tra metadata bảng và `flyway_schema_history` (tên script V1, tên script + checksum của V2, và các bản ghi V5/V6 đã áp dụng) để chọn đúng 1 trong 6 lineage được hỗ trợ (`CURRENT`, `LEGACY_RELATIONSHIPS_V2`, `CURRENT_DOCUMENTATION_V5`, `CURRENT_PULL_REQUESTS_V5`, `CURRENT_DOCUMENTATION_V5_SOURCE_CHANGES_V6`, `CURRENT_PULL_REQUESTS_V5_SOURCE_CHANGES_V6`) kết hợp với `classpath:db/migration-common`. |
| FR-BE—09.10 | **(LD-405 — Bảo toàn dữ liệu & lịch sử khi nâng cấp)** Với database mới, chạy `CURRENT` sử dụng migration hợp nhất `V5__documentation_code_relationships_and_pull_requests.sql`. Với database đã ở V4 hoặc đã áp dụng một nhánh V5/V6 riêng, nâng cấp tiếp phần schema còn thiếu ở version kế tiếp mà không thay đổi checksum, không xóa dữ liệu hiện có và không dùng `Flyway.repair()` để ghi đè lịch sử. |
| FR-BE—09.11 | **(LD-216 & LD-405 — Kiểm thử tự động & CI)** Đảm bảo đầy đủ test migration fresh/existing DB (`DocumentationCodeRelationshipMigrationTest`), test chọn lineage (`FlywayMigrationLineageSelectorTest`), test API quan hệ (`DocumentationCodeRelationshipApiTest`) và tích hợp vào `.github/workflows/ci.yml` (job `github-integration-test` chạy Maven `verify` và chạy `DocumentationCodeRelationshipApiTest` trên PostgreSQL 16 với `spring.jpa.hibernate.ddl-auto=validate`). |

## 3. API, Schema và Giao diện

### 3.1. Endpoints API Quan hệ Tài liệu – Mã nguồn

Tất cả endpoint yêu cầu header `X-User-Id` hợp lệ được Backend BFF chuyển tiếp.

| Method | Endpoint | Chức năng | Yêu cầu |
|---|---|---|---|
| `GET` | `/api/repositories/{repositoryId}/code-entities` | Liệt kê danh sách `CodeEntityResponse` đang `active = true` của repository (sắp xếp theo `path`, `lineStart`) | FR-BE—09.5, 09.7 |
| `GET` | `/api/repositories/{repositoryId}/documentation` | Liệt kê danh sách `DocumentationArtifactResponse` thuộc user trong repository (mới nhất trước) | FR-BE—09.5, 09.7 |
| `GET` | `/api/documentation/{documentId}` | Lấy thông tin chi tiết và nội dung Markdown của một tài liệu | FR-BE—09.5, 09.7 |
| `GET` | `/api/documentation/{documentId}/code-entities` | Lấy danh sách `CodeEntityResponse` đang active được liên kết với tài liệu (điều hướng Tài liệu → Code) | FR-BE—09.5, 09.6 |
| `PUT` | `/api/documentation/{documentId}/code-entities` | Thay thế danh sách thực thể mã nguồn liên kết với tài liệu; body `{"codeEntityIds": ["<uuid>", ...]}` | FR-BE—09.4, 09.7 |
| `GET` | `/api/documentation/code-entities/{entityId}/documents` | Lấy danh sách `DocumentationArtifactResponse` được liên kết với một code entity (điều hướng Code → Tài liệu) | FR-BE—09.6, 09.7 |

Ví dụ cấu trúc dữ liệu trao đổi:
- **Request `PUT /api/documentation/{documentId}/code-entities`:** `{"codeEntityIds": ["3fa85f64-5717-4562-b3fc-2c963f66afa6"]}` (cho phép `[]` để xóa hết liên kết; tối đa 500 UUID).
- **Response `CodeEntityResponse`:** `{"id": "...", "entityType": "method", "name": "OrderService.createOrder", "path": "src/main/java/OrderService.java", "lineStart": 42, "lineEnd": 68, "sourceUrl": "https://github.com/owner/repo/blob/<sha>/src/main/java/OrderService.java#L42-L68", "sourceCommit": "<sha>"}`.

### 3.2. Cấu trúc Bảng Dữ liệu & Ràng buộc

| Bảng | Cột chính | Khóa & Ràng buộc toàn vẹn |
|---|---|---|
| `documentation_artifacts` | `id` (UUID), `repository_id` (UUID), `owner_user_id`, `generation_job_id`, `markdown`, `source_commit`, `created_at`, `updated_at` | PK `id`; FK `repository_id` $\rightarrow$ `repositories(id) ON DELETE CASCADE`; `UNIQUE (generation_job_id)` |
| `code_entities` | `id` (UUID), `repository_id` (UUID), `stable_key` (SHA-256), `entity_type`, `name`, `path`, `line_start`, `line_end`, `source_url`, `source_commit`, `active`, `last_seen_at` | PK `id`; FK `repository_id` $\rightarrow$ `repositories(id) ON DELETE CASCADE`; `UNIQUE (repository_id, stable_key)` |
| `documentation_code_relationships` | `id` (UUID), `documentation_id` (UUID), `code_entity_id` (UUID), `created_at` | PK `id`; FK `documentation_id` $\rightarrow$ `documentation_artifacts(id) ON DELETE CASCADE`; FK `code_entity_id` $\rightarrow$ `code_entities(id) ON DELETE CASCADE`; `UNIQUE (documentation_id, code_entity_id)` |

### 3.3. Thành phần Giao diện Frontend (`DocumentationManagement.jsx`)

| Thành phần UI | Chức năng hiển thị & tương tác | Yêu cầu |
|---|---|---|
| Danh sách liên kết Code Entity trên màn hình Tài liệu | Hiển thị các `class`, `method`, `function`, `endpoint` đang liên kết với tài liệu kèm đường dẫn tệp và khoảng dòng | FR-BE—09.5 (LD-214) |
| Trình chọn / cập nhật liên kết mã nguồn | Cho phép người dùng chọn từ danh sách code entity của repository hoặc gỡ liên kết và lưu qua API `PUT .../code-entities` | FR-BE—09.4 (LD-213) |
| Liên kết điều hướng hai chiều | Mở trực tiếp mã nguồn trên GitHub qua `sourceUrl` (`#L<start>-L<end>`) hoặc chọn một code entity để xem danh sách tài liệu liên quan | FR-BE—09.6 (LD-215) |

## 4. Luồng chính

### 4.1. Luồng khởi động & chọn Migration Lineage (LD-405)

1. Khi GitHub Integration Service khởi động, `FlywayMigrationLineageConfig` kích hoạt `FlywayMigrationLineageSelector.select(dataSource)`.
2. Selector kiểm tra trạng thái database:
   - Nếu database trống (chưa có bảng ứng dụng và chưa có `flyway_schema_history`), chọn lineage `CURRENT` (`db/migration-current`) chạy `V5__documentation_code_relationships_and_pull_requests.sql`.
   - Nếu database đã có `flyway_schema_history`, xác minh `V1__init_github_integration.sql`, đối chiếu tên script và checksum của `V2` (phân biệt `V2__documentation_code_relationships.sql` của legacy với `V2__document_review_workflow.sql` của current), sau đó kiểm tra lịch sử `V5`/`V6` để chọn 1 trong 6 lineage tương thích.
3. Flyway thực thi các migration còn thiếu của lineage đã chọn cùng thư mục dùng chung `classpath:db/migration-common` (V8, V9) mà không làm thay đổi checksum các phiên bản cũ.

### 4.2. Luồng trích xuất thực thể, liên kết và điều hướng (LD-211)

1. Khi người dùng yêu cầu sinh tài liệu cho repository, `DocumentationGenerationService` gọi `DocumentationCodeRelationshipService.recordGeneration(...)` kèm kết quả phân tích AST và `RepositorySnapshot`.
2. Service tạo/cập nhật `DocumentationArtifact` gắn với `generationJobId`, `repositoryId`, `ownerUserId` và `sourceCommit`.
3. Service duyệt các tệp phân tích hợp lệ, tính `stable_key = SHA-256(path + \0 + entityType + \0 + qualifiedName)` và thực hiện upsert vào `code_entities` kèm `sourceUrl` trỏ đúng commit và dòng `#L<start>-L<end>`. Các thực thể không còn xuất hiện trong snapshot đầy đủ được chuyển sang `active = false`.
4. Người dùng mở màn hình quản lý tài liệu (`DocumentationManagement.jsx`) để xem danh sách code entity khả dụng của repository, chọn các thực thể liên quan và lưu qua `PUT /api/documentation/{documentId}/code-entities`.
5. Khi xem tài liệu, người dùng nhấn vào liên kết thực thể mã nguồn để mở trực tiếp dòng code tương ứng trên GitHub (`sourceUrl`), hoặc tra cứu ngược danh sách tài liệu gắn với một code entity qua `GET /api/documentation/code-entities/{entityId}/documents`.

## 5. Luồng lỗi

| Trường hợp | HTTP / Điều kiện | Kết quả |
|---|---|---|
| Lịch sử Flyway bất nhất (có bảng ứng dụng nhưng thiếu `flyway_schema_history`, có migration `success = false`, hoặc checksum V2 không nhận diện được) | Khởi động service (`FlywayMigrationLineageSelector`) | Chủ động ném ngoại lệ và dừng khởi động; không tự ý `repair` hay bỏ qua validation |
| Truyền `codeEntityIds` không tồn tại, đang `active = false`, hoặc thuộc repository khác | `400 Bad Request` (`PUT /api/documentation/{id}/code-entities`) | Từ chối cập nhật và giữ nguyên toàn bộ liên kết hợp lệ hiện có của tài liệu |
| Truyền `codeEntityIds` rỗng (`null`) hoặc vượt quá $500$ phần tử | `400 Bad Request` (Bean Validation `@NotNull @Size(max = 500)`) | Từ chối request ngay tại controller |
| Tài liệu hoặc code entity không tồn tại hoặc không thuộc quyền sở hữu của `X-User-Id` | `404 Not Found` / `403 Forbidden` | Từ chối truy cập dữ liệu của người dùng khác |
| Repository chưa được kết nối hoặc người dùng không sở hữu repository | `403 Forbidden` / `404 Not Found` (`requireOwnedRepository`) | Ngăn đọc/ghi danh sách thực thể và tài liệu của repository |

## 6. Quy tắc nghiệp vụ

- **Tính bất biến của định danh code entity:** `stable_key` chỉ phụ thuộc đường dẫn tệp, loại thực thể và tên định danh; việc thêm/xóa dòng phía trên làm thay đổi `line_start`/`line_end` và `source_url` nhưng tuyệt đối không tạo bản ghi `code_entities` mới hay làm đứt liên kết tài liệu đã gắn.
- **Ẩn mềm thay vì xóa cứng thực thể biến mất:** Thực thể biến mất khỏi mã nguồn được đánh dấu `active = false` và bị ẩn khỏi kết quả API, nhưng bản ghi trong `documentation_code_relationships` vẫn được giữ lại để tự động khôi phục nếu thực thể được thêm lại.
- **Toàn vẹn dây chuyền khi xóa repository:** Khi xóa repository khỏi workspace, toàn bộ `documentation_artifacts`, `code_entities` và `documentation_code_relationships` phụ thuộc tự động bị xóa theo ràng buộc `ON DELETE CASCADE`.
- **Tính nguyên tử khi cập nhật liên kết:** Thao tác `replaceLinks` kiểm tra hợp lệ toàn bộ tập `codeEntityIds` đã khử trùng lặp trước khi xóa liên kết cũ; nếu có bất kỳ ID nào không hợp lệ, giao dịch rollback và không làm mất liên kết cũ.
- **Bảo toàn lịch sử migration:** Tuyệt đối không sửa đổi nội dung/checksum của các file migration đã phát hành; mọi biến thể nhánh lịch sử V5/V6 được xử lý thông qua thư mục lineage riêng biệt.

## 7. Tiêu chí chấp nhận

- **AC-BE-09.1 (LD-212):** Các bảng `documentation_artifacts`, `code_entities`, `documentation_code_relationships` khởi tạo đầy đủ khóa chính UUID, khóa ngoại `ON DELETE CASCADE` và các ràng buộc `UNIQUE` (`generation_job_id`, `(repository_id, stable_key)`, `(documentation_id, code_entity_id)`).
- **AC-BE-09.2 (LD-212):** Khi số dòng code thay đổi nhưng `path`, `entity_type`, `name` giữ nguyên, `CodeEntity.id` và liên kết tài liệu giữ nguyên, `sourceUrl` cập nhật đúng số dòng mới; khi entity bị xóa rồi khôi phục, ID và liên kết cũ hoạt động trở lại.
- **AC-BE-09.3 (LD-213):** Quá trình sinh tài liệu tự động lưu `DocumentationArtifact` và các `CodeEntity`; API `PUT /api/documentation/{documentId}/code-entities` khử trùng lặp ID, cập nhật liên kết thành công và từ chối ID không hợp lệ/khác repository mà không xóa liên kết cũ.
- **AC-BE-09.4 (LD-214 & LD-215):** API và giao diện `DocumentationManagement.jsx` hiển thị danh sách code entity liên kết với tài liệu, hỗ trợ điều hướng sang đúng commit/dòng code trên GitHub (`sourceUrl`) và tra cứu ngược danh sách tài liệu từ một code entity.
- **AC-BE-09.5 (Bảo mật):** Người dùng không sở hữu repository hoặc tài liệu không thể đọc hoặc sửa đổi liên kết tài liệu – code của người dùng khác.
- **AC-BE-09.6 (LD-405 — Fresh & Existing DB Migration):** Database mới migrate qua `CURRENT` khớp hoàn toàn với JPA entity mapping (`hibernate.hbm2ddl.auto=validate`); database cũ ở V4 nâng cấp lên V5+ không mất dữ liệu hiện có.
- **AC-BE-09.7 (LD-405 — Lineage Compatibility):** `FlywayMigrationLineageSelector` chọn đúng lineage cho cả 6 kịch bản lịch sử (trống, legacy V2, Documentation V5, Pull Requests V5, và các nhánh đã có Source Changes V6), giữ nguyên checksum cũ và từ chối lịch sử lỗi.
- **AC-BE-09.8 (LD-216 & LD-405 — CI):** Pipeline `.github/workflows/ci.yml` chạy thành công toàn bộ bộ test Maven của `github-integration-service` và chạy `DocumentationCodeRelationshipApiTest` trên PostgreSQL 16 với `ddl-auto=validate`.

## 8. Kiểm thử

- **Kiểm thử migration & ràng buộc schema (`DocumentationCodeRelationshipMigrationTest`):** Kiểm tra chạy Flyway từ đầu trên H2 chế độ PostgreSQL kết hợp `hibernate.hbm2ddl.auto=validate`, kiểm tra nâng cấp database từ V4 lên V5+ bảo toàn dữ liệu cũ, kiểm tra lỗi vi phạm unique constraint và hành vi `ON DELETE CASCADE` khi xóa repository.
- **Kiểm thử lựa chọn lineage (`FlywayMigrationLineageSelectorTest`):** Kiểm thử toàn bộ các tổ hợp lịch sử Flyway (database mới, legacy V2, Documentation V5, Pull Requests V5, Source Changes V6) và các trường hợp từ chối checksum sai hoặc migration thất bại.
- **Kiểm thử tích hợp API quan hệ (`DocumentationCodeRelationshipApiTest` & `ApiRoutePermissionsTest`):** Kiểm tra trọn vẹn các endpoint đọc/ghi quan hệ, khử trùng lặp ID, kiểm soát quyền sở hữu theo `X-User-Id`, tính ổn định ID khi đổi số dòng và vòng đời `active`/`inactive` của thực thể mã nguồn.
- **Tích hợp CI (`.github/workflows/ci.yml` — job `github-integration-test`):** Thực thi `mvn --batch-mode --no-transfer-progress -f services/github-integration-service/pom.xml verify` và chạy `DocumentationCodeRelationshipApiTest` kết nối trực tiếp tới PostgreSQL 16 với `-Dspring.jpa.hibernate.ddl-auto=validate`.