# FR-DR-01 Review và xử lý drift: chấp nhận hoặc sửa gợi ý của AI

| Mục | Nội dung |
|---|---|
| Feature Jira | epic LD-9 Documentation Drift Detection & Review |
| Task đã làm | LD-161 (LD-162 Review Detected Drift, LD-163 Display Drift Evidence, LD-164 Generate Drift Resolution Suggestions, LD-165 Implement Accept Edit Dismiss Actions, LD-166 Test Drift Review & Resolution); PR #151 |
| Người thực hiện | Lê Hiền Hải Đăng. Finding, bằng chứng, AI review có `suggested_update` và các trạng thái `open` / `acknowledged` / `resolved` / `dismissed` đã có từ FR-AI-05, FR-AI-07, FR-AI-08 của Huy; LD-161 thêm phần chấp nhận gợi ý của AI, nguyên văn hoặc sau khi sửa |
| Thành phần | AI Service (cổng 8001): `app/drift_models.py` (`ResolutionUpdate`, `FindingResolution`, `ResolutionEvent` thêm `accepted_update`), `app/drift_review.py` (`resolve`). GitHub Integration Service: `dto/DriftResolutionRequest` (thêm `acceptedUpdate`), `service/DriftAnalysisService.resolveFinding`. Không có giao diện (xem mục 1) |
| Tác nhân | Người review drift, qua API của GitHub Integration Service |
| Phụ thuộc | FR-AI-05 (báo cáo drift của một Pull Request), FR-AI-07 (mức độ, lý do, bằng chứng), FR-AI-08 (AI review, trạng thái xử lý finding) của Huy |

## 1. Mô tả

Trước LD-161, mỗi finding đã có gợi ý sửa tài liệu của AI (`ai_review.suggested_update`), nhưng khi đặt finding thành `resolved` thì hệ thống không ghi lại nội dung tài liệu nào được chấp nhận. LD-161 cho người review gửi kèm `acceptedUpdate` khi resolve: gợi ý của AI nguyên văn, hoặc bản đã sửa. Nội dung đó được lưu vào trạng thái xử lý và lịch sử của finding. Dismiss giữ như cũ, bắt buộc có lý do.

Các subtask đã có từ trước được dùng lại, không viết lại:

- LD-162 (xem các finding đã phát hiện), LD-163 (bằng chứng `X1` code diff, `D1..` dòng tài liệu, `C1` commit, `T1..` Jira): FR-AI-05, FR-AI-07.
- LD-164 (gợi ý sửa): `ai_review.suggested_update` của FR-AI-08. Gợi ý chỉ có khi AI không phản bác finding (`verdict` khác `disputed`).

**Giao diện đã bị bỏ.** PR #151 ban đầu thêm nút **Accept suggestion** / **Edit suggestion** vào trang Documentation Drift. Ngày 17/11/2026, ma trận phân quyền (PR #153, [Docs/rbac-screen-flow.md](../rbac-screen-flow.md)) bỏ dòng #16 Drift Alerts & Review cho mọi role. Trang Documentation Drift và test `tests/test_frontend_drift.py` bị xoá, Backend BFF từ chối mọi route `/api/repositories/{id}/drift/**`. Khi gộp `main` vào PR #151 (20/11/2026), phần giao diện và test giao diện được bỏ theo quyết định đó. Chức năng hiện chỉ có ở mức API. Muốn dùng lại trên web, nhóm cần mở lại dòng #16 cho một role.

Phạm vi: nội dung được chấp nhận chỉ được ghi vào báo cáo drift, chưa được ghi vào tài liệu đã lưu (chưa tạo phiên bản mới theo FR-AI-06 của Linh). Bước ghi vào tài liệu cần task riêng.

## 2. Yêu cầu chức năng

| ID | Yêu cầu |
|---|---|
| FR-DR-01.1 | **LD-162 – LD-164 (có sẵn).** Báo cáo drift có cho mỗi finding: mức độ, loại drift, lý do, bằng chứng, ý kiến và giải thích của AI, gợi ý sửa (`ai_review.suggested_update`) và trạng thái xử lý. |
| FR-DR-01.2 | **LD-165, chấp nhận nguyên văn.** `PUT .../resolution` với `status = resolved` và `acceptedUpdate` = gợi ý của AI. |
| FR-DR-01.3 | **LD-165, chấp nhận bản đã sửa.** Cũng request đó, `acceptedUpdate` là nội dung người review đã sửa. Khoảng trắng đầu và cuối bị bỏ. |
| FR-DR-01.4 | **Lưu.** AI Service lưu nội dung vào `resolution.accepted_update` và vào dòng lịch sử mới (`history[].accepted_update`), cùng người thực hiện (`actor` = id của user đang đăng nhập, do GitHub Integration gắn) và thời điểm. Gợi ý gốc của AI giữ nguyên trong `ai_review`. |
| FR-DR-01.5 | **Ràng buộc.** `acceptedUpdate` chỉ được gửi cùng `status = resolved`. Chuỗi rỗng hoặc chỉ có khoảng trắng được coi như không gửi. Tối đa 20.000 ký tự. |
| FR-DR-01.6 | **Mở lại.** `status = open` xoá `accepted_update` hiện hành của finding; dòng lịch sử cũ vẫn giữ nội dung đã chấp nhận. Gửi lại đúng trạng thái, ghi chú và nội dung hiện có thì không thêm dòng lịch sử. |
| FR-DR-01.7 | **Dismiss (có sẵn).** Bắt buộc có lý do, không đi kèm nội dung chấp nhận. `resolved` không kèm nội dung vẫn hợp lệ, dùng khi người review tự sửa tài liệu. |

## 3. API

| Method | Endpoint | Gọi từ | Kết quả | Yêu cầu |
|---|---|---|---|---|
| PUT | `/api/repositories/{id}/drift/reports/{reportId}/findings/{findingId}/resolution` (GitHub Integration) | Client có mã nội bộ; Backend BFF hiện từ chối route này với mọi role | `200` + finding đã cập nhật | FR-DR-01.2 – 01.7 |
| PUT | `/drift/reports/{id}/findings/{finding}/resolution` (AI Service) | GitHub Integration | `200` + finding đã cập nhật | FR-DR-01.4 – 01.6 |

Body gửi GitHub Integration (trường mới: `acceptedUpdate`):

```json
{"status": "resolved", "acceptedUpdate": "Read a total with `GET /api/carts/:id` (currency in the query)."}
```

GitHub Integration chuyển sang AI Service, gắn `actor` là user đang đăng nhập:

```json
{"status": "resolved", "actor": "42", "accepted_update": "Read a total with `GET /api/carts/:id` (currency in the query)."}
```

Phần `resolution` của finding trả về:

```json
{"status": "resolved", "actor": "42", "note": null,
 "accepted_update": "Read a total with `GET /api/carts/:id` (currency in the query).",
 "updated_at": "2026-11-17T16:20:00Z",
 "history": [{"status": "resolved", "actor": "42", "note": null,
              "accepted_update": "Read a total with `GET /api/carts/:id` (currency in the query).",
              "at": "2026-11-17T16:20:00Z"}]}
```

## 4. Dữ liệu

Không có bảng hay migration mới. Trường mới nằm trong báo cáo drift của AI Service, được lưu theo FR-DR-02:

| Model (AI Service) | Trường mới | Nội dung |
|---|---|---|
| `ResolutionUpdate` (body PUT) | `accepted_update` | Nội dung được chấp nhận, ≤ 20.000 ký tự, chỉ với `resolved` |
| `FindingResolution` | `accepted_update` | Nội dung đang được chấp nhận; `null` khi chưa chấp nhận hoặc đã mở lại |
| `ResolutionEvent` (mỗi dòng lịch sử) | `accepted_update` | Nội dung được chấp nhận ở lần thay đổi đó |

GitHub Integration: `DriftResolutionRequest(status, note, acceptedUpdate)`; constructor 2 tham số cũ vẫn giữ để code đang gọi không phải sửa.

## 5. Luồng chính

1. Người review lấy báo cáo drift của một Pull Request (FR-AI-05) và đọc gợi ý sửa của từng finding.
2. Người review gửi `PUT .../resolution` với `status = resolved` và `acceptedUpdate` (gợi ý nguyên văn hoặc đã sửa).
3. GitHub Integration kiểm tra người gọi là người tạo báo cáo, kiểm tra `acceptedUpdate`, rồi gửi sang AI Service kèm `actor`.
4. AI Service ghi `accepted_update`, thêm một dòng lịch sử, cập nhật tiến độ review của báo cáo và lưu báo cáo (FR-DR-02).
5. Response trả finding đã cập nhật, có `resolution.accepted_update` và dòng lịch sử mới.

## 6. Luồng lỗi

| Trường hợp | HTTP | Kết quả |
|---|---|---|
| `acceptedUpdate` đi cùng `status` khác `resolved` | `400` (GitHub Integration) / `422` (AI Service) | `{"message": "An accepted update can only be given when resolving a finding."}`; AI Service: `{"detail": "An accepted update can only be given when resolving a finding"}` |
| `acceptedUpdate` dài hơn 20.000 ký tự | `400` / `422` | `{"message": "acceptedUpdate must be 20000 characters or fewer."}`; AI Service trả lỗi validation |
| Gọi qua Backend BFF (trình duyệt) | `403` | Route drift bị ma trận phân quyền từ chối với mọi role |
| Các lỗi có sẵn: trạng thái sai, dismiss không lý do, ghi chú > 2000 ký tự, báo cáo của người khác (`403`), không tìm thấy (`404`), AI Service lỗi (`502`) | | Như FR-AI-08 của Huy |

Lỗi không làm đổi trạng thái của finding.

## 7. Quy tắc nghiệp vụ

- Gợi ý của AI và nội dung người review chấp nhận là hai trường riêng, nên vẫn so được nội dung đã sửa với gợi ý gốc.
- Chỉ người review quyết định chấp nhận: AI không tự đổi trạng thái finding, và không đổi loại hay mức độ (FR-AI-08).
- Kiểm tra `acceptedUpdate` ở cả GitHub Integration lẫn AI Service, để AI Service cũng an toàn khi được gọi thẳng.
- GitHub Integration chỉ cho người tạo báo cáo xử lý finding của báo cáo đó (FR-AI-05).

## 8. Tiêu chí chấp nhận

- Resolve kèm gợi ý nguyên văn: `resolution.accepted_update` và dòng lịch sử mới chứa đúng gợi ý; tiến độ review tăng một finding `resolved`.
- Resolve kèm bản đã sửa: lưu đúng nội dung đã sửa (đã bỏ khoảng trắng đầu và cuối); gợi ý gốc trong `ai_review` không đổi.
- Gửi `acceptedUpdate` với `acknowledged`, `open` hay `dismissed`: bị từ chối, trạng thái không đổi.
- Mở lại thì xoá nội dung đang chấp nhận, nhưng lịch sử vẫn giữ nó; gửi lại đúng nội dung cũ không thêm dòng lịch sử.

## 9. Kiểm thử

| Test | Số test | Nội dung |
|---|---|---|
| `ai-service/tests/test_drift_review_history.py` (phần LD-161) | 4 | Chấp nhận gợi ý được lưu vào `resolution` và lịch sử, tiến độ review tăng; nội dung đã sửa được lưu (bỏ khoảng trắng), mở lại thì xoá nhưng lịch sử còn; `accepted_update` với `acknowledged`, `open`, `dismissed` trả `422`, gửi lại đúng nội dung không thêm lịch sử; API `PUT /drift/reports/{id}/findings/{finding}/resolution` nhận nội dung đã sửa và trả `422` khi không phải `resolved`. Chạy bằng `python -m pytest` (job CI **AI Service Build and Test**) |
| `DriftAnalysisServiceTest.acceptedSuggestionIsForwardedOnlyWhenResolving` | 1 | AI Service giả (`MockRestServiceServer`): `acceptedUpdate` với `acknowledged` bị `400`; với `resolved` thì được bỏ khoảng trắng và chuyển sang AI Service đúng body `{"status", "actor", "accepted_update"}`. Chạy bằng `mvn verify` (job CI **GitHub Integration Service Test**) |

Test giao diện `test_ai_suggestion_is_accepted_as_is_or_after_editing` của PR #151 đã bị bỏ cùng trang Documentation Drift (mục 1).
