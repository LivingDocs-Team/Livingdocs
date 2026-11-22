-- Approval and merge policies (one row per policy type) and Manager approval delegations.
CREATE TABLE approval_policies (
    policy_type VARCHAR(20) PRIMARY KEY CHECK (policy_type IN ('APPROVAL', 'MERGE')),
    settings TEXT NOT NULL,
    updated_by VARCHAR(100) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE approval_delegations (
    id UUID PRIMARY KEY,
    delegator_user_id VARCHAR(100) NOT NULL,
    delegate_user_id VARCHAR(100) NOT NULL,
    reason VARCHAR(500),
    starts_at TIMESTAMP WITH TIME ZONE NOT NULL,
    ends_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_approval_delegations_delegator ON approval_delegations (delegator_user_id, created_at DESC);
CREATE INDEX idx_approval_delegations_delegate ON approval_delegations (delegate_user_id, ends_at DESC);
