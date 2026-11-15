-- LD-68: Pull Request và commit nhận từ webhook GitHub hoặc lấy bù khi đồng bộ

-- Mỗi webhook GitHub có một X-GitHub-Delivery riêng; GitHub gửi lại thì bỏ qua
CREATE TABLE github_webhook_deliveries (
    delivery_id     VARCHAR(100) PRIMARY KEY,
    event           VARCHAR(50)  NOT NULL,
    github_repo_id  BIGINT       NOT NULL,
    received_at     TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE github_commits (
    id              UUID PRIMARY KEY,
    repository_id   UUID         NOT NULL REFERENCES repositories (id) ON DELETE CASCADE,
    sha             VARCHAR(40)  NOT NULL,
    branch          VARCHAR(255),
    message         VARCHAR(4000),  -- cắt bớt nếu dài hơn
    author_name     VARCHAR(255),
    author_login    VARCHAR(100),
    committed_at    TIMESTAMP WITH TIME ZONE,
    html_url        VARCHAR(500),
    source          VARCHAR(20)  NOT NULL,  -- WEBHOOK / SYNC
    received_at     TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_github_commits_repo_sha UNIQUE (repository_id, sha)
);

CREATE TABLE github_pull_requests (
    id              UUID PRIMARY KEY,
    repository_id   UUID         NOT NULL REFERENCES repositories (id) ON DELETE CASCADE,
    pr_number       INTEGER      NOT NULL,
    title           VARCHAR(1000),
    state           VARCHAR(20)  NOT NULL,  -- open / closed (theo GitHub)
    author_login    VARCHAR(100),
    head_ref        VARCHAR(255),
    head_sha        VARCHAR(40),
    base_ref        VARCHAR(255),
    html_url        VARCHAR(500),
    created_at      TIMESTAMP WITH TIME ZONE,
    updated_at      TIMESTAMP WITH TIME ZONE,
    closed_at       TIMESTAMP WITH TIME ZONE,
    merged_at       TIMESTAMP WITH TIME ZONE,
    source          VARCHAR(20)  NOT NULL,  -- WEBHOOK / SYNC
    received_at     TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_github_pull_requests_repo_number UNIQUE (repository_id, pr_number)
);

CREATE INDEX idx_github_repositories_github_repo_id ON repositories (github_repo_id);
