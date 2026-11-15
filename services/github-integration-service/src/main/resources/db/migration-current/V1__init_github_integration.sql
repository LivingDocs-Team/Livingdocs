-- Epic 2: GitHub Account Connection
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

-- Epic 3: Repository Management
CREATE TABLE repositories (
    id              UUID PRIMARY KEY,
    workspace_id    VARCHAR(100) NOT NULL,
    connection_id   UUID         NOT NULL REFERENCES github_connections (id),
    github_repo_id  BIGINT       NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    default_branch  VARCHAR(255),
    is_private      BOOLEAN      NOT NULL DEFAULT FALSE,
    html_url        VARCHAR(500),
    status          VARCHAR(20)  NOT NULL,  -- CONNECTED / SYNCING / ERROR / DISCONNECTED
    last_synced_at  TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_repositories_workspace_repo UNIQUE (workspace_id, github_repo_id)
);

CREATE INDEX idx_repositories_workspace ON repositories (workspace_id);
CREATE INDEX idx_repositories_connection ON repositories (connection_id);
