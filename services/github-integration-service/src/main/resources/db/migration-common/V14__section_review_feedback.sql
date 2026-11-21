ALTER TABLE document_workflow_audit ADD COLUMN section_start_offset INTEGER;
ALTER TABLE document_workflow_audit ADD COLUMN section_end_offset INTEGER;
ALTER TABLE document_workflow_audit ADD COLUMN section_quote VARCHAR(4000);
ALTER TABLE document_workflow_audit ADD CONSTRAINT ck_audit_section_feedback CHECK (
    (section_start_offset IS NULL AND section_end_offset IS NULL AND section_quote IS NULL)
    OR (section_start_offset IS NOT NULL AND section_end_offset IS NOT NULL AND section_quote IS NOT NULL
        AND document_version IS NOT NULL AND section_start_offset >= 0
        AND section_end_offset > section_start_offset)
);
