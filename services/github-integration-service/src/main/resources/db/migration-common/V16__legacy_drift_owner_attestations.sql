-- Populate from authenticated historical records linking the exact report ID
-- to its original user and connected repository. Leave unverifiable IDs absent.
-- The deployment database operator supplies these rows, with a source reference
-- that identifies the evidence used to verify each association.
CREATE TABLE legacy_drift_owner_attestations (
    report_id VARCHAR(64) PRIMARY KEY,
    repository_id UUID NOT NULL REFERENCES repositories (id) ON DELETE CASCADE,
    owner_user_id VARCHAR(100) NOT NULL,
    evidence_reference VARCHAR(500) NOT NULL CHECK (TRIM(evidence_reference) <> '')
);
