-- Postgres bootstrap for local development and CI.
-- The container entrypoint already creates the owner role and database.
-- This script adds the low-privilege runtime role used by the API.
--
-- Run it as the schema owner:
--   psql -h 127.0.0.1 -U restroos_owner -d restroos -v ON_ERROR_STOP=1 -f infra/postgres/init.sql
--
-- Safe to re-run: role creation is guarded and grants are idempotent.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'restroos_app') THEN
    CREATE ROLE restroos_app LOGIN PASSWORD 'restroos_app_dev_password';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE restroos TO restroos_app;
GRANT USAGE ON SCHEMA public TO restroos_app;

-- Future tables created by the owner (Alembic runs as restroos_owner) are
-- automatically usable by the runtime role. The runtime role never owns a
-- table, which is what makes RLS enforceable (owners bypass policies).
ALTER DEFAULT PRIVILEGES FOR ROLE restroos_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO restroos_app;
ALTER DEFAULT PRIVILEGES FOR ROLE restroos_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO restroos_app;
