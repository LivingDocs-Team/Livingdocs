CREATE TABLE auto_update_policies (
    repository_id UUID NOT NULL REFERENCES repositories (id) ON DELETE CASCADE,
    scope VARCHAR(10) NOT NULL CHECK (scope IN ('REPOSITORY', 'MODULE', 'DOCUMENT')),
    target VARCHAR(500) NOT NULL,
    on_commit BOOLEAN NOT NULL,
    on_pull_request BOOLEAN NOT NULL,
    PRIMARY KEY (repository_id, scope, target)
);
