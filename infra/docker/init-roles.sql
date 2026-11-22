-- Runs once on the postgres container's first init (docker-entrypoint-initdb.d).
-- The ops role: migrations run as it, never as the app role (spec §5). Creating
-- it here (not in a migration) avoids the circularity of a migration role that
-- must exist before any migration runs.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'markbook_ops') THEN
    CREATE ROLE markbook_ops LOGIN PASSWORD 'markbook_ops_dev_password';
  END IF;
END
$$;

GRANT ALL ON DATABASE markbook TO markbook_ops;
GRANT ALL ON SCHEMA public TO markbook_ops;
