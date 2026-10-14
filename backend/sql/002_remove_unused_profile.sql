-- Explicit destructive migration. Existing values in these four columns are removed.
-- Apply with the matching API release; do not run old API code afterwards.
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE public.members DROP COLUMN IF EXISTS birth_date;
ALTER TABLE public.members DROP COLUMN IF EXISTS phone;
ALTER TABLE public.members DROP COLUMN IF EXISTS created_at;
ALTER TABLE public.login_sessions DROP COLUMN IF EXISTS created_at;
COMMIT;
