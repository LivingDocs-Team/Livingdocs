# FR-GH-05 Nhận Pull Request và commit từ GitHub

| Mục | Nội dung |
|---|---|
| Feature Jira | epic LD-6 GitHub Integration |
| Task đã làm | LD-68 (LD-69 Receive GitHub Pull Request Events, LD-70 Receive GitHub Commit Events, LD-71 Store Pull Request Data, LD-72 Store Commit Data, LD-73 Test PR & Commit Ingestion); LD-401 gộp vào `main` (PR #86) |
| Người thực hiện | Lê Hiền Hải Đăng |
| Thành phần | GitHub Integration Service (cổng 8082): `controller/GitHubWebhookController`, `webhook/WebhookSignatureVerifier`, `service/IngestionService`, `controller/RepositoryActivityController`, entity `WebhookDelivery`, `RepositoryCommit`, `RepositoryPullRequest`, migration `V5__pull_requests_and_commits.sql`. Frontend: `RepositoryActivity.jsx` (nút **PRs & commits** trên trang Repository Management) |
| Tác nhân | GitHub App (gửi webhook `push`, `pull_request`); Developer xem danh sách trên frontend (qua Backend BFF) |
| Phụ thuộc | FR-GH-02 (repo phải có trong workspace), FR-GH-03 (mỗi lần đồng bộ lấy bù dữ liệu). Dữ liệu được dùng tiếp ở FR-GH-06 |

## 1. Mô tả

GitHub App gửi webhook mỗi khi có push hoặc thay đổi Pull Request trên repo đã cài app. Service kiểm chữ ký, bỏ qua event lặp lại, rồi lưu commit và Pull Request vào database cho từng repo của workspace. Để không mất dữ liệu khi webhook bị lỡ (service tắt, mạng lỗi), mỗi lần đồng bộ (FR-GH-03) thành công còn lấy bù các commit gần nhất và 30 Pull Request cập nhật gần nhất. Người dùng xem danh sách Pull Request và commit của repo ngay trên trang Repository Management. Commit mới trên nhánh mặc định và Pull Request đang mở có commit head mới được chuyển sang bước phát hiện thay đổi mã nguồn (FR-GH-06).

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-GH-05.1 | GitHub gọi thẳng `POST /api/github/webhook` (không qua Backend, không cần mã nội bộ). Request phải có header `X-Hub-Signature-256` = `sha256=` + HMAC-SHA256 của nguyên body với `GITHUB_WEBHOOK_SECRET`, so sánh theo thời gian hằng. Chữ ký thiếu hoặc sai: `401 WEBHOOK_SIGNATURE_INVALID`, không ghi gì. |
| FR-GH-05.2 | Service chưa cấu hình `GITHUB_WEBHOOK_SECRET`: mọi webhook bị từ chối `503 WEBHOOK_NOT_CONFIGURED`, không xử lý payload. |
| FR-GH-05.3 | Event `ping` (GitHub gửi khi vừa lưu cấu hình webhook) trả `200 {"status": "PONG"}`. |
| FR-GH-05.4 | Thiếu header `X-GitHub-Event` hoặc `X-GitHub-Delivery`, hoặc body không phải JSON hợp lệ: `400 BAD_REQUEST`. Delivery có body hỏng không bị ghi nhận, nên GitHub gửi lại cùng delivery với body đúng vẫn được xử lý. |
| FR-GH-05.5 | Chỉ xử lý event `push` và `pull_request`. Event khác, hoặc repo (theo `repository.id` của GitHub) chưa được thêm vào workspace nào: `202 {"status": "IGNORED"}`, không ghi gì. |
| FR-GH-05.6 | Chống xử lý lặp: mỗi `X-GitHub-Delivery` chỉ xử lý một lần. GitHub gửi lại cùng delivery: `202 {"status": "DUPLICATE"}`, không ghi lần hai. Xử lý xong: `202 {"status": "PROCESSED"}`. |
| FR-GH-05.7 | Event `push`: chỉ nhận push lên nhánh (`refs/heads/...`). Push tag hoặc xoá nhánh (`deleted: true`) không tạo commit. Mỗi commit lưu SHA, nhánh, thông điệp (cắt còn 4000 ký tự), tên và login tác giả, thời điểm, link; **không lưu email**. |
| FR-GH-05.8 | Mỗi commit chỉ có một dòng cho mỗi repo (theo SHA). Cùng commit được đẩy lên nhánh khác bằng delivery khác thì không tạo dòng mới. |
| FR-GH-05.9 | Event `pull_request`: lưu số, tiêu đề, trạng thái (`open`/`closed` theo GitHub), login tác giả, nhánh và commit head, nhánh base, link, thời điểm tạo, cập nhật, đóng, merge. Mỗi Pull Request chỉ có một dòng cho mỗi repo (theo số); event mới cập nhật dòng đó. Event đến muộn có `updated_at` cũ hơn dữ liệu đã lưu thì không ghi đè. |
| FR-GH-05.10 | Lấy bù khi đồng bộ: mỗi lần FR-GH-03 thành công, lưu các commit gần nhất của nhánh vừa đồng bộ (tối đa 20, từ kết quả đồng bộ) và 30 Pull Request cập nhật gần nhất (mọi trạng thái), nguồn `SYNC`. Không lấy được danh sách Pull Request thì chỉ ghi log, lần đồng bộ vẫn thành công. |
| FR-GH-05.11 | Xem dữ liệu: `GET /api/repositories/{id}/pull-requests` (tối đa 100, cập nhật gần nhất trước) và `GET /api/repositories/{id}/commits` (tối đa 100, mới nhất trước). Chỉ người xem được repo (FR-GH-02) mới xem được: repo không có thì `404`, không có quyền thì `403`. |
| FR-GH-05.12 | Gỡ repo khỏi workspace thì xoá luôn Pull Request và commit của repo đó. |
| FR-GH-05.13 | Sau khi lưu: commit mới trên nhánh mặc định của repo, và Pull Request đang mở có commit head mới (`opened`, `synchronize`), được chuyển sang phát hiện thay đổi mã nguồn (FR-GH-06). Bước này chạy nền sau khi transaction lưu webhook đã commit, để GitHub nhận phản hồi ngay (GitHub chỉ chờ webhook khoảng 10 giây). |
| FR-GH-05.14 | Frontend: nút **PRs & commits** trên mỗi repo của workspace mở panel liệt kê Pull Request (`#số tiêu đề` có link, nhãn Open / Closed / Merged, `head → base`, tác giả, thời điểm cập nhật) và commit (7 ký tự đầu SHA, dòng đầu thông điệp có link, nhánh, tác giả, thời điểm). Không có dữ liệu thì báo "No pull requests received yet." / "No commits received yet."; lỗi thì hiện thông báo tiếng Anh theo mã lỗi. |

## 3. API

| Method | Endpoint | Gọi từ | Kết quả | Yêu cầu |
|---|---|---|---|---|
| POST | `/api/github/webhook` | GitHub App, header `X-GitHub-Event`, `X-GitHub-Delivery`, `X-Hub-Signature-256` | `202 {"status": "PROCESSED" \| "DUPLICATE" \| "IGNORED"}`; `200 {"status": "PONG"}` | FR-GH-05.1 – 05.10, 05.13 |
| GET | `/api/repositories/{id}/pull-requests` | Frontend qua Backend BFF | `200` danh sách Pull Request | FR-GH-05.11 |
| GET | `/api/repositories/{id}/commits` | Frontend qua Backend BFF | `200` danh sách commit | FR-GH-05.11 |

Ví dụ response rút gọn:

```json
[{"number": 8, "title": "Add invoice export", "state": "open", "merged": false, "authorLogin": "lamhuyy",
  "headRef": "feature/export", "headSha": "<40 ký tự hex>", "baseRef": "main",
  "htmlUrl": "https://github.com/acme/shop/pull/8", "createdAt": "2026-11-06T02:00:00Z",
  "updatedAt": "2026-11-06T03:00:00Z", "mergedAt": null, "source": "WEBHOOK"}]

[{"sha": "<40 ký tự hex>", "branch": "main", "message": "Fix invoice totals\n\nRounds to cents.",
  "authorName": "Hai Dang", "authorLogin": "d3r-bbb", "committedAt": "2026-11-06T03:01:00Z",
  "htmlUrl": "https://github.com/acme/shop/commit/abcdef1", "source": "WEBHOOK"}]
```

Lời gọi GitHub khi lấy bù: `GET /repos/{owner}/{repo}/pulls?state=all&sort=updated&direction=desc&per_page=30`. Commit lấy bù có sẵn trong kết quả đồng bộ, không gọi thêm GitHub.

## 4. Dữ liệu

Migration `V5__pull_requests_and_commits.sql`:

| Bảng | Cột chính | Ràng buộc |
|---|---|---|
| `github_webhook_deliveries` | `delivery_id` (khoá chính), `event`, `github_repo_id`, `received_at` | Mỗi delivery một dòng: chống xử lý lặp |
| `github_commits` | `repository_id`, `sha`, `branch`, `message` (≤ 4000), `author_name`, `author_login`, `committed_at`, `html_url`, `source` (`WEBHOOK` / `SYNC`), `received_at` | Duy nhất theo (`repository_id`, `sha`); xoá theo repo (`ON DELETE CASCADE`) |
| `github_pull_requests` | `repository_id`, `pr_number`, `title`, `state`, `author_login`, `head_ref`, `head_sha`, `base_ref`, `html_url`, `created_at`, `updated_at`, `closed_at`, `merged_at`, `source`, `received_at` | Duy nhất theo (`repository_id`, `pr_number`); xoá theo repo |

Thêm chỉ mục `idx_github_repositories_github_repo_id` trên `repositories (github_repo_id)` để tìm nhanh repo của webhook. Response trả `merged = true` khi `merged_at` có giá trị.

## 5. Luồng chính

**Webhook:**

1. Có push hoặc thay đổi Pull Request; GitHub gửi `POST /api/github/webhook` kèm chữ ký.
2. Service kiểm secret đã cấu hình, kiểm chữ ký, trả `PONG` nếu là `ping`, kiểm header và đọc JSON.
3. Tìm các repo của workspace có `github_repo_id` khớp; không có thì `IGNORED`. Delivery đã xử lý thì `DUPLICATE`.
4. Ghi delivery, lưu commit (push) hoặc cập nhật Pull Request, trả `202 PROCESSED`.
5. Sau khi lưu xong, chạy nền bước phát hiện thay đổi (FR-GH-06) cho commit mới trên nhánh mặc định hoặc Pull Request đang mở có head mới.

**Lấy bù khi đồng bộ:** sau mỗi lần FR-GH-03 thành công, lưu commit gần nhất của nhánh và gọi GitHub lấy 30 Pull Request cập nhật gần nhất.

**Xem trên frontend:** Developer bấm **PRs & commits** trên một repo; frontend gọi hai API xem dữ liệu, hiện panel; bấm **Hide PRs & commits** để ẩn. Panel tải lại sau mỗi lần đồng bộ.

Cấu hình webhook cho GitHub App (secret, kênh chuyển tiếp smee khi chạy trên máy, chọn event Push và Pull request): xem `services/github-integration-service/README.md`, mục "Nhận Pull Request và commit (LD-68)".

## 6. Luồng lỗi

| Mã | HTTP | Khi nào | Dữ liệu |
|---|---|---|---|
| `WEBHOOK_NOT_CONFIGURED` | 503 | Chưa cấu hình `GITHUB_WEBHOOK_SECRET` | Không xử lý |
| `WEBHOOK_SIGNATURE_INVALID` | 401 | Chữ ký thiếu, sai định dạng, hoặc không khớp | Không ghi |
| `BAD_REQUEST` | 400 | Thiếu `X-GitHub-Event` / `X-GitHub-Delivery`; body không phải JSON | Không ghi; delivery chưa bị đánh dấu |
| (`IGNORED`) | 202 | Event khác `push` / `pull_request`; repo không thuộc workspace nào; push tag hoặc xoá nhánh | Không ghi commit / Pull Request |
| (`DUPLICATE`) | 202 | Cùng `X-GitHub-Delivery` đã xử lý | Không ghi lần hai |
| `FORBIDDEN` / `NOT_FOUND` | 403 / 404 | Xem dữ liệu của repo không có quyền / không tồn tại | |

Lỗi GitHub khi lấy danh sách Pull Request lúc đồng bộ không làm hỏng lần đồng bộ (chỉ ghi log).

## 7. Quy tắc nghiệp vụ

- Webhook chỉ tin chữ ký HMAC; không có secret thì không nhận webhook nào.
- Một delivery chỉ được xử lý một lần; một commit (SHA) và một Pull Request (số) chỉ có một dòng cho mỗi repo.
- Dữ liệu Pull Request mới hơn không bị event cũ ghi đè.
- Không lưu email của tác giả commit.
- Một repo GitHub có thể nằm trong nhiều workspace; webhook ghi dữ liệu cho từng repo đó.
- Chỉ commit trên nhánh mặc định và Pull Request đang mở có head mới được chuyển sang phát hiện thay đổi; commit trên nhánh khác vẫn được lưu và xem được.

## 8. Tiêu chí chấp nhận

- Push lên nhánh của repo trong workspace: commit xuất hiện ở `GET .../commits` với `source = WEBHOOK`.
- GitHub gửi lại cùng delivery: trả `DUPLICATE`, số commit không đổi.
- Chữ ký sai hoặc thiếu: `401`, không có dữ liệu nào được ghi; chưa cấu hình secret: `503`; body hỏng: `400` và gửi lại cùng delivery với body đúng vẫn `PROCESSED`.
- Event Pull Request cũ đến muộn không ghi đè dữ liệu mới.
- Webhook bị lỡ: lần đồng bộ sau lấy bù đủ commit và Pull Request.
- Người khác không xem được dữ liệu; gỡ repo thì dữ liệu của repo bị xoá.
- Đã chạy thử với GitHub thật qua kênh smee trên repo `d3r-bbb/Livingdocs` trong đợt test ngày 06/11/2026.

## 9. Kiểm thử

Test Java nằm trong `services/github-integration-service/src/test/java/com/livingdocs/github/`, chạy bằng `mvn verify` (job CI **GitHub Integration Service Test**). Test giao diện chạy trong job CI **Frontend E2E Test**.

| Test | Số test | Nội dung |
|---|---|---|
| `GitHubWebhookIngestionTest` | 9 | `@SpringBootTest` + MockMvc + H2, GitHub giả: push lưu commit; cùng delivery chỉ xử lý một lần, cùng commit chỉ lưu một lần; Pull Request cập nhật tại chỗ, event cũ không ghi đè; chữ ký thiếu hoặc sai bị từ chối; JSON hỏng trả `400` và không "dùng hết" delivery (LD-401); ping, event khác, tag, repo ngoài workspace không ghi gì; đồng bộ lấy bù commit và Pull Request; đồng bộ vẫn thành công khi không liệt kê được Pull Request; người khác không xem được, gỡ repo thì xoá dữ liệu |
| `webhook/WebhookSignatureVerifierTest` | 3 | Khớp ví dụ chữ ký trong tài liệu GitHub; body bị sửa hoặc secret khác thì sai; header thiếu, sai định dạng, secret rỗng thì sai |
| `controller/GitHubWebhookControllerTest` | 1 | Chưa cấu hình secret: `503 WEBHOOK_NOT_CONFIGURED`, không xử lý payload (LD-401) |
| `tests/test_repository_activity.py` | 3 | Playwright, backend giả: panel liệt kê Pull Request (nhãn Open / Merged, link) và commit, ẩn panel; repo chưa có dữ liệu hiện danh sách rỗng; lỗi hiện thông báo tiếng Anh, không hiện thông báo tiếng Việt của service |
