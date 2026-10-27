# Kết nối tài khoản GitHub (GitHub Account Connection)

| Mục | Nội dung |
|---|---|
| Người làm | Đặng Lê Hiển Hải (TV2) |
| Jira | Story LD-22; task LD-53 (Sprint 1), LD-23 (Sprint 3: chuyển về frontend sau khi kết nối, xử lý khi người dùng bấm Cancel) |
| Code | `services/github-integration-service`, package `com.livingdocs.github` |
| Phụ thuộc | Không. File này cũng mô tả **nền tảng chung của service** (mục 2), các chức năng Repository Management, Repository Synchronization, Repository Analysis Input dựng trên nền tảng này |

## 1. Mục tiêu

Người dùng LivingDocs liên kết tài khoản GitHub qua một **GitHub App** (OAuth user-to-server), để hệ thống đọc được các repository mà người dùng chọn khi cài app. Hệ thống lưu token GitHub đã mã hoá, tự làm mới token, cho xem trạng thái kết nối và cho ngắt kết nối.

## 2. Nền tảng chung của service

### 2.1 Công nghệ

- Java 21, Maven, `spring-boot-starter-parent` 3.5.6. Artifact `github-integration-service`, version `0.1.0`.
- Dependency: `spring-boot-starter-web`, `spring-boot-starter-data-jpa`, `spring-boot-starter-validation`, `spring-boot-starter-actuator`, `flyway-core`, `flyway-database-postgresql`, `postgresql` (runtime), `springdoc-openapi-starter-webmvc-ui` 2.8.9. Test: `spring-boot-starter-test`, `h2`.
- Database PostgreSQL 16, schema tạo bằng Flyway, Hibernate `ddl-auto: validate`.
- Gọi HTTP ra ngoài bằng Spring `RestClient`. DTO dùng Java `record`, JSON bằng Jackson.
- Class main: `GithubIntegrationServiceApplication` với `@SpringBootApplication` và `@ConfigurationPropertiesScan`.
- Package con: `client`, `config`, `controller`, `dto`, `entity`, `exception`, `repository`, `security`, `service`, `sync`.

### 2.2 Cấu hình `src/main/resources/application.yml`

```yaml
server:
  port: ${SERVER_PORT:8082}
spring:
  application:
    name: github-integration-service
  config:
    import: optional:file:.env[.properties]   # đọc biến bí mật từ file .env cạnh pom.xml, không commit .env
  datasource:
    url: ${DB_URL:jdbc:postgresql://localhost:5433/github_integration}
    username: ${DB_USERNAME:livingdocs}
    password: ${DB_PASSWORD:livingdocs}
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
github:
  client-id: ${GITHUB_CLIENT_ID:}
  client-secret: ${GITHUB_CLIENT_SECRET:}
  app-slug: ${GITHUB_APP_SLUG:livingdocs-dev-hai}
  redirect-uri: ${GITHUB_REDIRECT_URI:http://localhost:8082/api/github/callback}
  oauth-base-url: https://github.com
  api-base-url: https://api.github.com
security:
  token-encryption-key: ${TOKEN_ENCRYPTION_KEY:}
app:
  cors:
    allowed-origins: ${CORS_ALLOWED_ORIGINS:http://localhost:3000,http://localhost:5173}
  frontend-url: ${FRONTEND_URL:}
management:
  endpoints:
    web:
      exposure:
        include: health,info
springdoc:
  swagger-ui:
    path: /swagger-ui.html
```

`.env.example` (commit file này, không commit `.env`): `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_APP_SLUG`, `GITHUB_REDIRECT_URI`, `TOKEN_ENCRYPTION_KEY`, `FRONTEND_URL`, `CORS_ALLOWED_ORIGINS`, chỉ để giá trị mẫu hoặc để trống. `.gitignore` của service: `target/`, `.env`, `*.pem`, `secrets/`, `.idea/`, `*.iml`, `.vscode/`.

`config/GitHubProperties`: `@ConfigurationProperties(prefix = "github") record GitHubProperties(String clientId, String clientSecret, String appSlug, String redirectUri, String oauthBaseUrl, String apiBaseUrl)`.

### 2.3 Chạy và đóng gói

- `docker-compose.yml` cho môi trường dev: một service `postgres` image `postgres:16`, `POSTGRES_DB=github_integration`, `POSTGRES_USER=livingdocs`, `POSTGRES_PASSWORD=livingdocs`, cổng `5433:5432`, volume `github-db-data`.
- `Dockerfile` hai bước: build bằng `maven:3.9-eclipse-temurin-21` (`mvn -q -B dependency:go-offline` rồi `mvn -q -B package -DskipTests`), chạy bằng `eclipse-temurin:21-jre`, copy `target/github-integration-service-*.jar` thành `app.jar`, `EXPOSE 8082`, `ENTRYPOINT ["java","-jar","app.jar"]`.
- Swagger UI ở `/swagger-ui.html`. `config/OpenApiConfig` khai báo bean `OpenAPI` với title "LivingDocs - GitHub Integration Service", version "0.1.0".

### 2.4 Định danh người dùng

Mọi API (trừ callback) nhận header **`X-User-Id`** (chuỗi, id người dùng LivingDocs). Hằng số `static final String USER_HEADER = "X-User-Id"` đặt trong `GitHubConnectionController`, các controller khác import lại. Thiếu header thì trả `400 BAD_REQUEST`.

> Từ LD-396 (Nhân làm, không thuộc file này), frontend gọi qua Backend (BFF). Backend tự gắn `X-User-Id` và header `Authorization: Bearer <GITHUB_INTEGRATION_INTERNAL_SECRET>`; service từ chối request thiếu mã này bằng `401 INTERNAL_SERVICE_AUTH_REQUIRED`, trừ `GET /api/github/callback` và `/actuator/health`.

### 2.5 Định dạng lỗi

- `dto/ErrorResponse`: `record ErrorResponse(int status, String code, String message, Instant timestamp)`.
- `exception/ApiException extends RuntimeException` có `HttpStatus status`, `String code`, và các hàm tạo nhanh:

| Hàm | HTTP | `code` | Thông điệp |
|---|---|---|---|
| `notFound(msg)` | 404 | `NOT_FOUND` | `msg` |
| `badRequest(msg)` | 400 | `BAD_REQUEST` | `msg` |
| `forbidden(msg)` | 403 | `FORBIDDEN` | `msg` |
| `githubNotConnected()` | 409 | `GITHUB_NOT_CONNECTED` | "Bạn chưa kết nối GitHub hoặc kết nối đã bị ngắt. Hãy kết nối lại." |
| `githubReauthRequired()` | 401 | `GITHUB_REAUTH_REQUIRED` | "Token GitHub không còn hợp lệ. Hãy kết nối lại GitHub." |

- `exception/GlobalExceptionHandler` (`@RestControllerAdvice`) trả `ErrorResponse`:

| Exception | Kết quả |
|---|---|
| `ApiException` | HTTP và `code` của exception |
| `GitHubApiException` | `502 GITHUB_API_ERROR`, thông điệp an toàn (không lộ nội dung GitHub trả về): rate limit / token không còn hợp lệ / không tìm thấy / không kết nối được GitHub / "GitHub request failed (HTTP n)." |
| `MissingRequestHeaderException`, `MissingServletRequestParameterException` | `400 BAD_REQUEST` |
| `HttpMessageNotReadableException` | `400 BAD_REQUEST`, "Body không hợp lệ: sai định dạng JSON hoặc sai kiểu dữ liệu." |
| `MethodArgumentTypeMismatchException` | `400 BAD_REQUEST`, "Tham số '<tên>' không hợp lệ: <giá trị>" |
| `MethodArgumentNotValidException` | `400 VALIDATION_ERROR`, lỗi field đầu tiên dạng "field: message" |

Lỗi đồng bộ (`RepositorySyncException`) được mô tả ở file Repository Synchronization.

### 2.6 Cho frontend gọi API (CORS)

`config/CorsConfig implements WebMvcConfigurer`: đọc `app.cors.allowed-origins` (chuỗi, tách theo dấu phẩy, bỏ khoảng trắng và phần tử rỗng). Danh sách rỗng thì không đăng ký gì. Ngược lại `registry.addMapping("/api/**")` với `allowedOrigins(...)`, `allowedMethods("GET","POST","PUT","PATCH","DELETE","OPTIONS")`, `allowedHeaders("*")`, `exposedHeaders("Retry-After")`, `maxAge(3600)`.

### 2.7 Lỗi khi gọi GitHub: `exception/GitHubApiException`

`RuntimeException` giữ lại thông tin để tầng trên phân loại lỗi:

- Field: `int statusCode` (0 khi không nhận được phản hồi), `Long rateLimitRemaining` (header `x-ratelimit-remaining`), `Instant rateLimitReset` (header `x-ratelimit-reset`, giây epoch), `Long retryAfterSeconds` (header `retry-after`), `String responseBody`.
- Constructor: `(String message, boolean unauthorized)` (true thì statusCode = 401, ngược lại 0); `(String message, Throwable cause)` cho lỗi mạng; `(String message, int statusCode, HttpHeaders headers, String responseBody)` đọc các header trên (sai định dạng thì bỏ qua).
- Hàm: `isUnauthorized()` (401), `isNotFound()` (404), `isConflict()` (409), `isServerError()` (≥ 500), `isNetworkError()` (statusCode 0 và có cause), `isRateLimited()` (429; hoặc 403 kèm `x-ratelimit-remaining = 0`, hoặc có `retry-after`, hoặc body chứa "rate limit" không phân biệt hoa thường), `retryAt()` (now + retry-after nếu có, ngược lại rateLimitReset).

## 3. Dữ liệu

Migration `src/main/resources/db/migration/V1__init_github_integration.sql` tạo 2 bảng: `github_connections` (dưới đây) và `repositories` (xem file Repository Management).

```sql
CREATE TABLE github_connections (
    id                      UUID PRIMARY KEY,
    user_id                 VARCHAR(100) NOT NULL UNIQUE,
    github_user_id          BIGINT       NOT NULL,
    github_login            VARCHAR(100) NOT NULL,
    access_token            VARCHAR(2048), -- đã mã hoá AES-GCM
    refresh_token           VARCHAR(2048), -- đã mã hoá AES-GCM
    access_token_expires_at TIMESTAMP WITH TIME ZONE,
    status                  VARCHAR(20)  NOT NULL,  -- ACTIVE / INVALID / REVOKED
    created_at              TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at              TIMESTAMP WITH TIME ZONE NOT NULL
);
```

- `entity/ConnectionStatus`: enum `ACTIVE` (đang dùng được), `INVALID` (token hỏng, cần kết nối lại), `REVOKED` (người dùng đã ngắt).
- `entity/GitHubConnection` (`@Entity @Table(name = "github_connections")`): `UUID id` (`@GeneratedValue(strategy = GenerationType.UUID)`), `String userId` (unique), `Long githubUserId`, `String githubLogin`, `String accessToken` và `String refreshToken` (cả hai `@Convert(converter = EncryptedStringConverter.class)`, `length = 2048`), `Instant accessTokenExpiresAt`, `ConnectionStatus status` (`@Enumerated(EnumType.STRING)` + `@JdbcTypeCode(SqlTypes.VARCHAR)`), `Instant createdAt` (không cập nhật), `Instant updatedAt`. `@PrePersist` gán `createdAt = updatedAt = now`, `@PreUpdate` gán `updatedAt = now`. Có getter, setter cho mọi field.
- `repository/GitHubConnectionRepository extends JpaRepository<GitHubConnection, UUID>`: `Optional<GitHubConnection> findByUserId(String userId)`.

## 4. Bảo mật

### 4.1 Mã hoá token: `security/TokenEncryptor` (`@Component`)

- Thuật toán `AES/GCM/NoPadding`, IV 12 byte ngẫu nhiên (`SecureRandom`) cho mỗi lần mã hoá, tag 128 bit.
- Khoá: `@Value("${security.token-encryption-key}")`, giải mã Base64 chuẩn, phải đúng 32 byte. Thiếu khoá, sai Base64 hoặc sai độ dài thì ném `IllegalStateException` ngay khi khởi động (thông báo nói rõ lỗi).
- `encrypt(plain)`: `Base64(IV || ciphertext+tag)`. `decrypt(cipher)` làm ngược lại. `null` vào thì `null` ra. Lỗi giải mã ném `IllegalStateException("Không giải mã được token (sai TOKEN_ENCRYPTION_KEY?)")`.
- Tạo khoá trên Windows PowerShell: `$b = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); [Convert]::ToBase64String($b)`.

`security/EncryptedStringConverter` (`@Component @Converter`, `AttributeConverter<String, String>`) gọi `encrypt` khi ghi DB và `decrypt` khi đọc.

### 4.2 Mã chống giả mạo OAuth: `security/OAuthStateStore` (`@Component`)

- Lưu trong bộ nhớ: `ConcurrentHashMap<String, Entry>` với `record Entry(String userId, Instant expiresAt)`. TTL 10 phút. Có constructor nhận `Clock` để test.
- `create(userId)`: xoá các state đã hết hạn, sinh 24 byte ngẫu nhiên, mã hoá Base64 URL-safe không padding, lưu kèm userId và thời điểm hết hạn, trả về state.
- `consume(state)`: `null` thì trả rỗng. Xoá state khỏi map (chỉ dùng được 1 lần); không có hoặc đã hết hạn thì trả rỗng, ngược lại trả userId.

## 5. Gọi GitHub (phần OAuth): `client/GitHubClient` (`@Component`)

Constructor `(GitHubProperties props, RestClient.Builder builder)` tạo 2 client từ `builder.clone()`:

- `oauthClient`: base `oauthBaseUrl`, header `Accept: application/json`.
- `apiClient`: base `apiBaseUrl`, header `Accept: application/vnd.github+json` và `X-GitHub-Api-Version: 2022-11-28`.

| Hàm | Lời gọi GitHub |
|---|---|
| `GitHubTokenResponse exchangeCode(String code)` | `POST /login/oauth/access_token`, form urlencoded: `client_id`, `client_secret`, `code`, `redirect_uri` |
| `GitHubTokenResponse refreshToken(String refreshToken)` | `POST /login/oauth/access_token`, form: `client_id`, `client_secret`, `grant_type=refresh_token`, `refresh_token` |
| `GitHubUser getAuthenticatedUser(String accessToken)` | `GET /user`, `Authorization: Bearer <token>` |
| `void revokeGrant(String accessToken)` | `DELETE /applications/{clientId}/grant`, Basic auth `clientId:clientSecret`, body JSON `{"access_token": "<token>"}`. Bỏ qua mọi `RestClientException` (thu hồi theo kiểu cố gắng hết sức) |

- `record GitHubTokenResponse(access_token, expires_in, refresh_token, refresh_token_expires_in, token_type, scope, error, error_description)` (tên JSON snake_case, `@JsonIgnoreProperties(ignoreUnknown = true)`). GitHub trả HTTP 200 kèm `error` khi code sai, hết hạn hoặc đã dùng: khi đó ném `GitHubApiException("GitHub OAuth token exchange was rejected.", "bad_refresh_token".equals(error))`. Response rỗng thì ném `GitHubApiException("GitHub không trả về token", false)`.
- `record GitHubUser(Long id, String login)`.
- Chỉ gắn `Authorization: Bearer` khi token khác rỗng.
- Mọi lời gọi bọc trong hàm `call(Supplier<T>)`: `RestClientResponseException` thành `GitHubApiException("GitHub API returned HTTP <status>.", status, headers, body)`; `RestClientException` khác thành `GitHubApiException("Unable to contact GitHub API.", cause)`.

## 6. Xử lý nghiệp vụ: `service/GitHubConnectionService` (`@Service`)

Phụ thuộc: `GitHubProperties`, `GitHubClient`, `OAuthStateStore`, `GitHubConnectionRepository`, `ConnectedRepositoryRepository`. Hằng số `REFRESH_MARGIN = 5 phút`.

1. **`createAuthorizeUrl(userId)`**: `state = stateStore.create(userId)`. `authorizeUrl = {oauthBaseUrl}/login/oauth/authorize?client_id=..&redirect_uri=..&state=..`; `installUrl = {oauthBaseUrl}/apps/{appSlug}/installations/new?state=..` (dựng bằng `UriComponentsBuilder`, có `encode()`). Trả `AuthorizeUrlResponse(authorizeUrl, installUrl, state)`.
2. **`handleCallback(code, state)`** (`@Transactional`): `code` rỗng thì `ApiException.badRequest("Thiếu tham số code từ GitHub.")`. `userId = stateStore.consume(state)`, không có thì `badRequest("State không hợp lệ hoặc đã hết hạn. Hãy bấm 'Kết nối GitHub' lại từ đầu.")`. Đổi code lấy token, gọi `getAuthenticatedUser`. Tìm kết nối theo `userId`, chưa có thì tạo mới. Gán `userId`, `githubUserId`, `githubLogin`, token (bước 8), `status = ACTIVE`, lưu và trả về.
3. **`getStatus(userId)`** (`readOnly`): có kết nối thì `ConnectionResponse(status == ACTIVE, githubLogin, status.name(), createdAt, accessTokenExpiresAt)`, không có thì `ConnectionResponse.notConnected()` = `(false, null, "NOT_CONNECTED", null, null)`.
4. **`revoke(userId)`** (`@Transactional`): không có kết nối thì `notFound("Bạn chưa kết nối GitHub.")`. Có access token thì gọi `revokeGrant`. Xoá `accessToken`, `refreshToken`, `accessTokenExpiresAt`, đặt `REVOKED`, lưu. Mọi repo có `connectionId` này chuyển `DISCONNECTED`.
5. **`getActiveConnection(userId)`** (`@Transactional(noRollbackFor = ApiException.class)`), dùng trước mọi lời gọi GitHub: lấy kết nối `ACTIVE`, không có thì `githubNotConnected()`. Nếu `accessTokenExpiresAt` khác null và `now + 5 phút` đã qua thời điểm đó: không có refresh token thì `markInvalid` rồi `githubReauthRequired()`; có thì gọi `refreshToken`, cập nhật token, lưu; refresh lỗi (`GitHubApiException`) thì `markInvalid` rồi `githubReauthRequired()`.
6. **`findConnection(userId)`** (`readOnly`): `Optional`, không lọc trạng thái.
7. **`markInvalid(connection)`** (`@Transactional`): đặt `INVALID`, lưu, ghi log cảnh báo.
8. **Cập nhật token**: gán access token; refresh token chỉ gán khi GitHub trả về; `accessTokenExpiresAt = now + expires_in` (null nếu GitHub không trả `expires_in`).

## 7. API: `controller/GitHubConnectionController`

`@RestController @RequestMapping("/api/github")`, có annotation Swagger `@Tag`, `@Operation`. Constructor nhận `GitHubConnectionService` và `@Value("${app.frontend-url:}") String frontendUrl` (trim, null thành rỗng).

| Method | Path | Đầu vào | Kết quả |
|---|---|---|---|
| GET | `/api/github/authorize-url` | header `X-User-Id` | `200` `{"authorizeUrl": "...", "installUrl": "...", "state": "..."}` |
| GET | `/api/github/callback` | query `code`, `state`, `error` (đều không bắt buộc) | Xem bên dưới |
| GET | `/api/github/connection` | header `X-User-Id` | `200` `{"connected": true, "githubLogin": "d3r-bbb", "status": "ACTIVE", "connectedAt": "...", "tokenExpiresAt": "..."}` |
| DELETE | `/api/github/connection` | header `X-User-Id` | `204` |

**Callback**, trả `ResponseEntity<CallbackResponse>`:

- Có `error` mà `code` rỗng (người dùng bấm Cancel trên GitHub): coi như lỗi `ApiException(400, "GITHUB_ACCESS_DENIED", "Bạn chưa cho phép LivingDocs truy cập GitHub. Hãy bấm 'Kết nối GitHub' lại nếu muốn kết nối.")`, không gọi service.
- `frontendUrl` rỗng: gọi `handleCallback`, trả `200` `{"message": "Kết nối GitHub thành công", "githubLogin": "<login>"}`; lỗi thì để `GlobalExceptionHandler` xử lý.
- `frontendUrl` có giá trị: trả `302` với `Location` dựng bằng `UriComponentsBuilder.fromUriString(frontendUrl).queryParam(...).encode().build().toUri()`:
  - Thành công: `?github=connected&login=<githubLogin>`.
  - `ApiException`: `?github=error&reason=<code của exception>`.
  - `GitHubApiException`: ghi log, `?github=error&reason=GITHUB_API_ERROR`.

DTO (`dto/`): `AuthorizeUrlResponse(String authorizeUrl, String installUrl, String state)`, `CallbackResponse(String message, String githubLogin)`, `ConnectionResponse(boolean connected, String githubLogin, String status, Instant connectedAt, Instant tokenExpiresAt)` kèm `static notConnected()`.

## 8. Luồng sử dụng

1. Frontend gọi `GET /api/github/authorize-url`.
2. Lần đầu mở `installUrl` (cài GitHub App, chọn repo); các lần sau mở `authorizeUrl`.
3. Người dùng bấm Authorize, GitHub chuyển trình duyệt về `GET /api/github/callback?code=...&state=...`.
4. Service lưu kết nối `ACTIVE` rồi chuyển về `FRONTEND_URL?github=connected&login=...`.

## 9. Lỗi

| Tình huống | Kết quả |
|---|---|
| Thiếu `X-User-Id` | `400 BAD_REQUEST` |
| Callback thiếu `code` | `400 BAD_REQUEST` (hoặc `reason=BAD_REQUEST`) |
| `state` sai, hết hạn, đã dùng | `400 BAD_REQUEST` (hoặc `reason=BAD_REQUEST`) |
| Người dùng bấm Cancel | `400 GITHUB_ACCESS_DENIED` (hoặc `reason=GITHUB_ACCESS_DENIED`) |
| GitHub lỗi khi đổi code | `502 GITHUB_API_ERROR` (hoặc `reason=GITHUB_API_ERROR`) |
| Chưa kết nối mà dùng chức năng cần GitHub | `409 GITHUB_NOT_CONNECTED` |
| Token hết hạn, không làm mới được | `401 GITHUB_REAUTH_REQUIRED`, kết nối chuyển `INVALID` |
| Ngắt kết nối khi chưa kết nối | `404 NOT_FOUND` |

## 10. Test cần có

Profile test `src/test/resources/application-test.yml`: H2 `jdbc:h2:mem:testdb;MODE=PostgreSQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1`, `ddl-auto: none` (Flyway tạo bảng), `github.client-id: test-client-id`, `client-secret: test-client-secret`, `app-slug: livingdocs-test`, khoá test `AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=` (32 byte 0), ghi rõ `app.cors.allowed-origins` và `app.frontend-url: ""` để không phụ thuộc file `.env`.

- `TokenEncryptorTest` (5): mã hoá rồi giải mã ra đúng chuỗi gốc; cùng đầu vào cho 2 bản mã khác nhau; `null` giữ nguyên; từ chối khoá sai độ dài; từ chối thiếu khoá.
- `OAuthStateStoreTest` (3): state chỉ dùng 1 lần; state lạ bị từ chối; state quá 10 phút bị từ chối (dùng `Clock` giả).
- `GitHubConnectionControllerTest` (6, unit test với Mockito): không có `frontendUrl` thì trả JSON; thành công thì chuyển về `http://localhost:3000/?github=connected&login=d3r-bbb`; state sai thì `reason=BAD_REQUEST`; GitHub lỗi thì `reason=GITHUB_API_ERROR`; bấm Cancel thì `reason=GITHUB_ACCESS_DENIED` và không gọi service; bấm Cancel khi không có `frontendUrl` thì ném `ApiException` mã `GITHUB_ACCESS_DENIED`.
- `GitHubIntegrationFlowTest` (`@SpringBootTest`, `@AutoConfigureMockMvc`, `@ActiveProfiles("test")`, `@MockitoBean GitHubClient`): cả luồng kết nối, xem trạng thái (không lộ token, token trong DB khác token gốc), ngắt kết nối; callback với state giả bị `400`; thiếu header bị `400`; GitHub trả 401 thì kết nối chuyển `INVALID` và API trả `GITHUB_REAUTH_REQUIRED`.

## 11. Tiêu chí chấp nhận

- Gọi `authorize-url` thì `authorizeUrl` chứa `client_id` và `state`, `installUrl` chứa `/apps/<appSlug>/installations/new`.
- Callback hợp lệ tạo kết nối `ACTIVE`; token lưu trong DB đã mã hoá; API không bao giờ trả token.
- Có `FRONTEND_URL` thì trình duyệt được chuyển về frontend kèm kết quả trên URL.
- Token sắp hết hạn (còn dưới 5 phút) được tự làm mới; làm mới thất bại thì kết nối chuyển `INVALID`.
- Ngắt kết nối thì trạng thái `REVOKED`, `connected = false`, các repo của kết nối chuyển `DISCONNECTED`.
