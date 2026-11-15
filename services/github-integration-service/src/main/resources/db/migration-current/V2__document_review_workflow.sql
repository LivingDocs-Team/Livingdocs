CREATE TABLE document_workflows (
    id UUID PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL UNIQUE,
    document_title VARCHAR(200) NOT NULL,
    owner_user_id VARCHAR(100) NOT NULL,
    status VARCHAR(40) NOT NULL,
    submitted_document_version INTEGER,
    reviewer_user_id VARCHAR(100),
    staff_review_result VARCHAR(30),
    staff_comment VARCHAR(2000),
    manager_user_id VARCHAR(100),
    manager_decision VARCHAR(20),
    manager_comment VARCHAR(2000),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    submitted_at TIMESTAMP WITH TIME ZONE,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    decided_at TIMESTAMP WITH TIME ZONE,
    optimistic_version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX idx_document_workflows_owner_created
    ON document_workflows (owner_user_id, created_at DESC);
CREATE INDEX idx_document_workflows_queue
    ON document_workflows (status, submitted_at);
CREATE INDEX idx_document_workflows_reviewer
    ON document_workflows (reviewer_user_id, status);

CREATE TABLE document_workflow_audit (
    id UUID PRIMARY KEY,
    workflow_id UUID NOT NULL REFERENCES document_workflows (id),
    actor_user_id VARCHAR(100) NOT NULL,
    action VARCHAR(40) NOT NULL,
    previous_status VARCHAR(40),
    new_status VARCHAR(40) NOT NULL,
    comment VARCHAR(2000),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_document_workflow_audit_history
    ON document_workflow_audit (workflow_id, created_at);
