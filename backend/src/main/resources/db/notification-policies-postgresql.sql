CREATE TABLE IF NOT EXISTS notification_policies (
    event varchar(40) PRIMARY KEY CHECK (event IN (
        'REPOSITORY_CONNECTED', 'DOCUMENT_SUBMITTED', 'DOCUMENT_APPROVED', 'DOCUMENT_REJECTED',
        'AI_JOB_COMPLETED', 'AI_JOB_FAILED'
    )),
    recipients text[] NOT NULL CHECK (
        cardinality(recipients) BETWEEN 1 AND 50 AND array_position(recipients, NULL) IS NULL
    ),
    enabled boolean NOT NULL,
    updated_at timestamp with time zone NOT NULL DEFAULT now()
);
