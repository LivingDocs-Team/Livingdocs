# Livingdocs
BLCK

Link FIX TRACK AND REVIEW : https://docs.google.com/spreadsheets/d/1UYIFAOWyaIVJALOgs1vZeV7OEBJWqlsY/edit?gid=823422937#gid=823422937

link tl SRS: https://ut-team-lvdocs.atlassian.net/wiki/spaces/L/pages/458757/LivingDocs+Design+and+Implementation+of+an+AI-Assisted+Self-Updating+Document+System+for+Engineering+Teams


link jira: https://ut-team-lvdocs.atlassian.net/jira/software/projects/LD/boards/1/backlog



# LD-280 operational reference

| Area | Endpoint or setting |
| --- | --- |
| AI generation | The job owner can poll `GET /api/documentation/jobs/{jobId}` for status, progress and an error message. See [restart behavior](ai-service/README.md#job-monitoring-and-restarts-ld-281). |
| GitHub events | Use the delivery ID to find the ingestion outcome in GitHub Integration logs. Query `GET /api/repositories/{id}/source-changes` to inspect downstream source changes for a repository you can access. |
| Health | Backend and GitHub Integration expose `/actuator/health`. GitHub Integration checks AI and Code Analyzer at `/health`. Check the service endpoints individually to locate a failing dependency. |
| Workflow audit | `GET /api/document-workflows/{id}/history` uses workflow access rules and returns the workflow ID, actor, action and timestamp. |
| Administrative audit | `GET /api/admin/users/audit?page=0&size=20` requires `USER_AUDIT_VIEW`. It includes user account, role catalog and notification policy mutations. Profile audit stores changed field names. Policy audit stores the event and enabled state. |
| Administrative retention | Set `ADMIN_USER_AUDIT_RETENTION_DAYS` on the backend or in the Compose environment. A positive integer purges older administrative entries daily at 00:00 UTC. The default value of 0 disables automatic deletion. This setting applies to administrative records. |
| System analytics | System administrators query `GET /api/admin/system-analytics?from=…&to=…` with ISO 8601 timestamps and explicit offsets. The interval includes `from` and excludes `to`. AI job counts cover the current AI process and include its observation start. |
| Notification policies | System administrators list policies at `GET /api/admin/notification-policies` and save or delete a policy with `PUT` or `DELETE /api/admin/notification-policies/{event}`. A save takes `recipients` and `enabled`. Session-authenticated writes require CSRF. This API manages policy configuration. |
