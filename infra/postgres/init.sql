# Postgres bootstrap for local development.
# The container entrypoint already creates the owner role and database.
# This script adds the low-privilege runtime role used by the API.

CREATE ROLE restroos_app LOGIN PASSWORD 'restroos_app_dev_password';

GRANT CONNECT ON DATABASE restroos TO restroos_app;
GRANT USAGE ON SCHEMA public TO restroos_app;

-- Future tables created by the owner (Alembic runs as restroos_owner) are
-- automatically usable by the runtime role. The runtime role never owns a
-- table, which is what makes RLS enforceable (owners bypass policies).
ALTER DEFAULT PRIVILEGES FOR ROLE restroos_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO restroos_app;
ALTER DEFAULT PRIVILEGES FOR ROLE restroos_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO restroos_app;
