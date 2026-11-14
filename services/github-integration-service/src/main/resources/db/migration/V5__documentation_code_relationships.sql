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



