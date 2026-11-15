CREATE TABLE documentation_artifacts (
    id UUID PRIMARY KEY,
    repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    owner_user_id VARCHAR(100) NOT NULL,
    generation_job_id VARCHAR(100) NOT NULL UNIQUE,
    markdown TEXT,
    source_commit VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_documentation_artifacts_repository
    ON documentation_artifacts(repository_id, created_at DESC);

CREATE TABLE code_entities (
    id UUID PRIMARY KEY,
    repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    stable_key VARCHAR(64) NOT NULL,
    entity_type VARCHAR(30) NOT NULL,
    name VARCHAR(500) NOT NULL,
    path VARCHAR(1000) NOT NULL,
    line_start INTEGER,
    line_end INTEGER,
    source_url VARCHAR(2000) NOT NULL,
    source_commit VARCHAR(64),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_code_entities_repository_key UNIQUE(repository_id, stable_key)
);

CREATE INDEX idx_code_entities_repository_active
    ON code_entities(repository_id, active, path);

CREATE TABLE documentation_code_relationships (
    id UUID PRIMARY KEY,
    documentation_id UUID NOT NULL REFERENCES documentation_artifacts(id) ON DELETE CASCADE,
    code_entity_id UUID NOT NULL REFERENCES code_entities(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_documentation_code_pair UNIQUE(documentation_id, code_entity_id)
);

CREATE INDEX idx_documentation_code_entity
    ON documentation_code_relationships(code_entity_id);

-- LD-68: Pull Request và commit nhận từ webhook GitHub hoặc lấy bù khi đồng bộ
CREATE TABLE github_webhook_deliveries (
    delivery_id     VARCHAR(100) PRIMARY KEY,
    event           VARCHAR(50)  NOT NULL,
    github_repo_id  BIGINT       NOT NULL,
    received_at     TIMESTAMP WITH TIME ZONE NOT NULL
);

-- Mỗi webhook GitHub có một X-GitHub-Delivery riêng; GitHub gửi lại thì bỏ qua
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
