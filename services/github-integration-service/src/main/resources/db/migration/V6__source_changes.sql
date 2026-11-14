-- LD-116: thay đổi mã nguồn phát hiện từ commit / Pull Request, chờ bước cập nhật tài liệu (LD-128)

CREATE TABLE source_changes (
    id              UUID PRIMARY KEY,
    repository_id   UUID         NOT NULL REFERENCES repositories (id) ON DELETE CASCADE,
    trigger_type    VARCHAR(20)  NOT NULL,  -- COMMIT / PULL_REQUEST
    commit_sha      VARCHAR(40)  NOT NULL,  -- commit, hoặc commit head của Pull Request
    pr_number       INTEGER,
    status          VARCHAR(20)  NOT NULL,  -- PENDING / FAILED
    error_code      VARCHAR(50),
    error_message   VARCHAR(500),
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_source_changes_trigger UNIQUE (repository_id, trigger_type, commit_sha)
);

CREATE TABLE source_change_files (
    id                UUID PRIMARY KEY,
    source_change_id  UUID          NOT NULL REFERENCES source_changes (id) ON DELETE CASCADE,
    path              VARCHAR(1000) NOT NULL,
    previous_path     VARCHAR(1000),
    change_type       VARCHAR(20)   NOT NULL,  -- ADDED / MODIFIED / REMOVED / RENAMED
    language          VARCHAR(20),
    additions         INTEGER,
    deletions         INTEGER,
    skipped_reason    VARCHAR(50)              -- vì sao không tìm entity; null là đã tìm
);

CREATE INDEX idx_source_change_files_change ON source_change_files (source_change_id);

CREATE TABLE source_change_entities (
    file_id      UUID          NOT NULL REFERENCES source_change_files (id) ON DELETE CASCADE,
    kind         VARCHAR(20)   NOT NULL,
    name         VARCHAR(500)  NOT NULL,
    change_type  VARCHAR(20)   NOT NULL,  -- ADDED / MODIFIED / REMOVED
    start_line   INTEGER       NOT NULL,
    end_line     INTEGER       NOT NULL
);

CREATE INDEX idx_source_change_entities_file ON source_change_entities (file_id);



