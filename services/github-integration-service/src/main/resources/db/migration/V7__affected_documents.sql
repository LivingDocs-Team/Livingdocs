-- LD-122: tài liệu đã lưu (ai-service) có thể đã cũ vì một source change (LD-116)

ALTER TABLE source_changes ADD COLUMN documents_status VARCHAR(20);  -- PENDING / FOUND / FAILED; null khi source change FAILED
ALTER TABLE source_changes ADD COLUMN documents_error_code VARCHAR(50);
ALTER TABLE source_changes ADD COLUMN documents_error_message VARCHAR(500);

CREATE TABLE source_change_documents (
    id                UUID PRIMARY KEY,
    source_change_id  UUID          NOT NULL REFERENCES source_changes (id) ON DELETE CASCADE,
    document_id       VARCHAR(100)  NOT NULL,
    title             VARCHAR(500),
    version           INTEGER,                 -- phiên bản hiện hành của tài liệu lúc kiểm tra
    section_path      VARCHAR(1000) NOT NULL,  -- phần tài liệu (theo file) bị ảnh hưởng
    documents_file    VARCHAR(1000),           -- file mã nguồn mà phần này được sinh ra từ đó
    dependency        VARCHAR(20)   NOT NULL,  -- DIRECT / DEPENDENT (LD-125)
    reasons           VARCHAR(4000) NOT NULL   -- mỗi dòng một lý do
);

CREATE INDEX idx_source_change_documents_change ON source_change_documents (source_change_id);
