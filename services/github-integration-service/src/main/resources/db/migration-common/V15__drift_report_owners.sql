CREATE TABLE drift_report_owners (
    report_id VARCHAR(64) PRIMARY KEY,
    repository_id UUID NOT NULL REFERENCES repositories (id) ON DELETE CASCADE,
    owner_user_id VARCHAR(100) NOT NULL
);

CREATE INDEX idx_drift_report_owners_scope ON drift_report_owners (repository_id, owner_user_id);
