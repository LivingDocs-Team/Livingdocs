# Upgrading an existing LivingDocs PostgreSQL volume

The backend Compose database uses the PostgreSQL 16 role `livingdocs`. PostgreSQL only applies `POSTGRES_USER` and `POSTGRES_PASSWORD` when it initializes an empty volume. An existing `cnpm` cluster initialized with `postgres` retains its original roles and passwords.

## Rehearse on a separate volume

Use Bash or WSL for the binary dump redirects. Identify the running legacy backend database container and its Compose project and volume with `docker inspect`. Use an access-restricted directory outside the repository for backups. The source must be reachable using the legacy PostgreSQL credentials. Use `.pgpass` or your deployment's secret mechanism if socket authentication requires a password.

```bash
umask 077
docker exec "$LEGACY_DB_CONTAINER" pg_dump -U postgres -d cnpm -Fc > "$BACKUP_DIR/cnpm.dump"
docker exec "$LEGACY_DB_CONTAINER" pg_dumpall -U postgres --globals-only > "$BACKUP_DIR/globals.sql"
```

Keep the globals dump protected like credentials. Review it for site-specific roles and memberships. The standard Compose deployment has a single database owner. For deployments with additional roles, custom grants, tablespaces, or extensions, map them explicitly and verify access during rehearsal. The restore below intentionally remaps ownership and requires you to reapply any site-specific grants.

Choose a fresh volume name and a unique rehearsal project. Verify that the name is unused before creating it. Save this override outside the repository and substitute the new volume name.

```yaml
volumes:
  backend-db-data:
    external: true
    name: livingdocs-cnpm-upgraded-20261122
```

Set `BACKEND_DB_PASSWORD` in the rehearsal environment or its Compose environment file. Use different host ports from the running deployment, including the database ports, and set `FRONTEND_URL` to the rehearsal frontend URL. Provide the other required Compose settings as usual.

```bash
docker volume create livingdocs-cnpm-upgraded-20261122
dc=(docker compose -p livingdocs-upgrade-rehearsal -f compose.yaml -f "$UPGRADE_OVERRIDE")
"${dc[@]}" up -d --wait backend-db
"${dc[@]}" exec -T backend-db sh -ec '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  pg_restore -h backend-db -U livingdocs -d cnpm \
    --no-owner --no-acl --single-transaction
' < "$BACKUP_DIR/cnpm.dump"
"${dc[@]}" exec -T backend-db sh -ec '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  psql -X -h backend-db -U livingdocs -d cnpm -v ON_ERROR_STOP=1 \
    -c "SELECT current_database(), current_user, has_schema_privilege(current_user, '\''public'\'', '\''USAGE,CREATE'\'');"
'
"${dc[@]}" up -d --build --wait backend
```

The destination initializes the `livingdocs` login and password and makes it the database owner. Restoring as that role with `--no-owner --no-acl` gives it ownership of the restored application objects, including tables and sequences. The role must be able to use and create in the app schema, since Hibernate updates the schema at startup. Verify TCP authentication with the correct and a wrong password using the Compose service hostname. The PostgreSQL image can trust loopback connections. Verify the backend health endpoint and an authenticated application read and write. Compare representative row counts and records with the backup snapshot. Restart the database and backend, wait for health, and repeat the reads.

Review the effective audit policy before connecting a restored dataset to a running backend. To hold deletion during rehearsal, set the restored copy's `retention.auditLogDays` override to `0` before starting the backend, if an override exists. Otherwise set `ADMIN_USER_AUDIT_RETENTION_DAYS=0`. Restore the approved policy before opening the deployment for use.

## Cut over and retain rollback

After rehearsal, pause application writes and take a final backup. Restore it into another fresh destination volume using the same procedure. Stop the old stack without removing volumes. Use the original project name with an override pointing only `backend-db-data` at the final restored volume, so the other services keep their existing volumes. Validate the rendered volume names before starting. Keep the original volume, backup, and previous Compose revision until validation is complete.

If validation fails, stop the upgraded stack and start the previous revision with the original backend volume. Keep writes paused until you select a rollback or cutover path. Writes accepted on the new volume after cutover require reconciliation before rolling back.

LD-404 can exercise the PostgreSQL 16 legacy-role backup and restore, TCP password checks, ownership, backend startup, and restart persistence on generated data with `VERIFY_LEGACY_RESTORE=1 ./scripts/verify-compose.sh`.
