ALTER TABLE document_workflow_audit
    ADD COLUMN previous_reviewer_user_id VARCHAR(100);

ALTER TABLE document_workflow_audit
    ADD COLUMN new_reviewer_user_id VARCHAR(100);



