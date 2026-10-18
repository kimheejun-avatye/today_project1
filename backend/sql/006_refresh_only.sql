-- Explicit cutover: all existing logins end. Member/content tables are untouched.
-- Run together with 003_auth_retention.sql in one transaction; stop the API first.
DROP TABLE IF EXISTS public.refresh_tokens;
DROP TABLE IF EXISTS public.login_sessions;
CREATE TABLE public.refresh_tokens (
    id VARCHAR(36) PRIMARY KEY,
    member_id INTEGER NOT NULL UNIQUE REFERENCES public.members(id),
    digest VARCHAR(64) NOT NULL UNIQUE,
    expires_at INTEGER NOT NULL
);
CREATE INDEX ix_refresh_tokens_expires_at ON public.refresh_tokens(expires_at);
ALTER TABLE public.refresh_tokens ENABLE ROW LEVEL SECURITY;
DO $roles$
DECLARE role_name text;
BEGIN
  FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
      EXECUTE format('REVOKE ALL ON public.refresh_tokens FROM %I', role_name);
    END IF;
  END LOOP;
END;
$roles$;
