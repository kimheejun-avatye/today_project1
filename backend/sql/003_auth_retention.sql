-- Run as the database owner; callable only by explicitly authorized DB roles.
CREATE OR REPLACE FUNCTION public.haru_cleanup_auth()
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path = pg_catalog
AS $function$
--  변수 선언부
DECLARE
  current_second bigint := floor(extract(epoch FROM statement_timestamp()));
  cutoff bigint := current_second - 86400;
  verification_count integer;
  captcha_count integer;
  limit_count integer;
  token_count integer;
-- 실행부
BEGIN
  -- [기능1] 만료된 이메일 인증 데이터 삭제
  WITH candidates AS (
    SELECT id FROM public.email_verifications WHERE expires_at < cutoff
    FOR UPDATE SKIP LOCKED
  ) DELETE FROM public.email_verifications WHERE id IN (SELECT id FROM candidates);
  GET DIAGNOSTICS verification_count = ROW_COUNT;

  -- [기능2] 만료된 캡차 챌린지 데이터 삭제 
  WITH candidates AS (
    SELECT id FROM public.captcha_challenges WHERE expires_at < cutoff
    FOR UPDATE SKIP LOCKED
  ) DELETE FROM public.captcha_challenges WHERE id IN (SELECT id FROM candidates);
  GET DIAGNOSTICS captcha_count = ROW_COUNT;

  -- [기능3] 만료된 레이트 리밋 데이터 삭제
  WITH candidates AS (
    SELECT key FROM public.rate_limits
    WHERE started_at::bigint + 900 < cutoff AND blocked_until < cutoff
      AND last_sent_at::bigint + 60 < cutoff
    FOR UPDATE SKIP LOCKED
  ) DELETE FROM public.rate_limits WHERE key IN (SELECT key FROM candidates);
  GET DIAGNOSTICS limit_count = ROW_COUNT;

  WITH candidates AS (
    SELECT id FROM public.refresh_tokens WHERE expires_at <= current_second
    FOR UPDATE SKIP LOCKED
  ) DELETE FROM public.refresh_tokens WHERE id IN (SELECT id FROM candidates);
  GET DIAGNOSTICS token_count = ROW_COUNT;

  RETURN jsonb_build_object('email_verifications', verification_count,
    'captcha_challenges', captcha_count, 'rate_limits', limit_count,
    'refresh_tokens', token_count);

END;


$function$;
REVOKE ALL ON FUNCTION public.haru_cleanup_auth() FROM PUBLIC;
-- Supabase API roles may have default grants independent of PUBLIC.
DO $roles$
DECLARE role_name text;
BEGIN
  FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
      EXECUTE format('REVOKE ALL ON FUNCTION public.haru_cleanup_auth() FROM %I', role_name);
    END IF;
  END LOOP;
END;
$roles$;
