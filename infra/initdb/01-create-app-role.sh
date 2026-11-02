#!/bin/sh
set -eu

# Section 10/12 + Appendix A defect #5: the postgres Docker image makes
# POSTGRES_USER the bootstrap superuser, with no way to strip that
# afterward (Postgres refuses: "the bootstrap superuser must have the
# SUPERUSER attribute" — confirmed by actually trying it, not assumed).
# So POSTGRES_USER here is a throwaway bootstrap identity
# (icm_bootstrap, see infra/docker-compose.yml), used only in this
# script and never referenced by the app, migrations, or anything else.
# icm_owner — the role migrations actually run as — is created as a
# NON-superuser role and made the real owner of the database and the
# public schema, so it has full DDL rights without ever bypassing RLS.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'icm_owner') THEN
            -- CREATEDB: infra/scripts/restore.sh creates a fresh
            -- database per restore rehearsal (Section 12) rather than
            -- overwriting the live one; that needs CREATEDB, not
            -- SUPERUSER.
            CREATE ROLE icm_owner LOGIN CREATEDB PASSWORD '${ICM_OWNER_PASSWORD}';
        END IF;
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'icm_app') THEN
            CREATE ROLE icm_app LOGIN PASSWORD '${APP_DB_PASSWORD}';
        END IF;
    END
    \$\$;
    ALTER DATABASE "$POSTGRES_DB" OWNER TO icm_owner;
    ALTER SCHEMA public OWNER TO icm_owner;
    GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO icm_app;
SQL
