-- Run once after `alembic upgrade head` with an owner connection.
-- Audit rows are append-only: the runtime role must not rewrite history.
REVOKE UPDATE, DELETE ON audit_logs FROM restroos_app;

-- Defence in depth: the runtime role can read/write business data but cannot
-- change the schema or disable RLS.
REVOKE CREATE ON SCHEMA public FROM restroos_app;
