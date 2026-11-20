CREATE TABLE documentation_collections (
    id UUID PRIMARY KEY,
    workspace_id VARCHAR(100) NOT NULL,
    name VARCHAR(120) NOT NULL,
    name_key VARCHAR(240) NOT NULL,
    description VARCHAR(1000),
    repository_id UUID REFERENCES repositories(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX uq_documentation_collections_workspace_name
    ON documentation_collections (workspace_id, name_key);
CREATE INDEX idx_documentation_collections_repository
    ON documentation_collections (repository_id);

CREATE TABLE documentation_collection_documents (
    collection_id UUID NOT NULL REFERENCES documentation_collections(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documentation_artifacts(id) ON DELETE CASCADE,
    PRIMARY KEY (collection_id, document_id)
);

CREATE INDEX idx_documentation_collection_documents_document
    ON documentation_collection_documents (document_id);

CREATE TABLE documentation_owner_assignments (
    workspace_id VARCHAR(100) NOT NULL,
    document_id UUID NOT NULL REFERENCES documentation_artifacts(id) ON DELETE CASCADE,
    owner_user_id BIGINT NOT NULL CHECK (owner_user_id > 0),
    PRIMARY KEY (workspace_id, document_id)
);
