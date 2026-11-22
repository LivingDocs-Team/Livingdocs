# Revision workflow integration test

Run `pwsh -File tests/revision-e2e/run.ps1` from the repository root. The runner
creates a separate Compose project and records container output in
`revision-e2e.log`. It removes the test containers and their volumes afterward.

Spring Boot uses the production HTTP clients, PostgreSQL 16, Flyway and Hibernate
schema validation. The production FastAPI application runs in a separate process
with a fresh document store. GitHub, analyzer responses and the model answer are
fixtures. The Compose stack has no published ports and uses only fixture credentials.

The suite sends signed webhook deliveries, including an exact duplicate. It checks
that an expired lease can be reclaimed, a transient analyzer failure is retried and
the job finishes with a single proposed version. Staff review is required and
Manager approval checks the submitted document version and current GitHub SHA.
Rejection preserves the previously published content.

Run `pwsh -File tests/revision-e2e/run.ps1 -Restart -LogPath revision-restart.log`
to exercise a queued retry across process restarts. The first Spring Boot process
parks the job after a transient analyzer failure. FastAPI is recreated with the
same document volume, then a second Spring Boot process resumes the job against
the same PostgreSQL database. The test verifies the source-bound draft and its
publication after review.
