-- Supabase owner-only setup. Hourly; replaces same named job for the same owner.
-- https://supabase.com/docs/guides/cron/install
CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;
SELECT cron.schedule('haru-auth-cleanup-hourly', '0 * * * *',
  'SELECT public.haru_cleanup_auth();');
