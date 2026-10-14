-- Current application schema, 2026-10-13. No user data imported.

-- Run once on an empty public schema. Existing name collisions abort the transaction.

BEGIN;

SET LOCAL search_path = public;

CREATE TABLE captcha_challenges (
	id VARCHAR(36) NOT NULL, 
	code_digest VARCHAR(64) NOT NULL, 
	proof_digest VARCHAR(64), 
	expires_at INTEGER NOT NULL, 
	verified_at INTEGER, 
	consumed_at INTEGER, 
	attempts INTEGER NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_captcha_challenges_expires_at ON captcha_challenges (expires_at);

ALTER TABLE public.captcha_challenges ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.captcha_challenges FROM anon, authenticated;

CREATE TABLE members (
	id SERIAL NOT NULL, 
	email VARCHAR(254) NOT NULL, 
	password_hash TEXT, 
	name VARCHAR(80) NOT NULL, 
	nickname VARCHAR(40), 
	birth_date VARCHAR(10), 
	phone VARCHAR(30) NOT NULL, 
	google_subject VARCHAR(255), 
	privacy_consent_version VARCHAR(60), 
	privacy_consented_at INTEGER, 
	created_at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (password_hash IS NOT NULL OR google_subject IS NOT NULL), 
	UNIQUE (email), 
	UNIQUE (google_subject)
);

ALTER TABLE public.members ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.members FROM anon, authenticated;

CREATE TABLE rate_limits (
	key VARCHAR(300) NOT NULL, 
	count INTEGER NOT NULL, 
	started_at INTEGER NOT NULL, 
	blocked_until INTEGER NOT NULL, 
	last_sent_at INTEGER NOT NULL, 
	PRIMARY KEY (key)
);

ALTER TABLE public.rate_limits ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.rate_limits FROM anon, authenticated;

CREATE TABLE diaries (
	id SERIAL NOT NULL, 
	member_id INTEGER NOT NULL, 
	diary_date VARCHAR(10) NOT NULL, 
	content TEXT NOT NULL, 
	emotion VARCHAR(40) NOT NULL, 
	status VARCHAR(10) NOT NULL, 
	is_shared BOOLEAN NOT NULL, 
	version INTEGER NOT NULL, 
	updated_at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (member_id, diary_date), 
	CHECK (status IN ('DRAFT','FINAL')), 
	CHECK (NOT is_shared OR status = 'FINAL'), 
	FOREIGN KEY(member_id) REFERENCES members (id)
);

ALTER TABLE public.diaries ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.diaries FROM anon, authenticated;

CREATE TABLE email_verifications (
	id VARCHAR(36) NOT NULL, 
	member_id INTEGER, 
	email VARCHAR(254) NOT NULL, 
	purpose VARCHAR(30) NOT NULL, 
	code_digest VARCHAR(64) NOT NULL, 
	flow_digest VARCHAR(64) NOT NULL, 
	expires_at INTEGER NOT NULL, 
	verified_at INTEGER, 
	consumed_at INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(member_id) REFERENCES members (id)
);

ALTER TABLE public.email_verifications ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.email_verifications FROM anon, authenticated;

CREATE TABLE login_sessions (
	id VARCHAR(36) NOT NULL, 
	member_id INTEGER NOT NULL, 
	created_at INTEGER NOT NULL, 
	expires_at INTEGER NOT NULL, 
	revoked_at INTEGER, 
	refresh_revoked_at INTEGER, 
	csrf_digest VARCHAR(64) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(member_id) REFERENCES members (id)
);

CREATE INDEX ix_login_sessions_member_id ON login_sessions (member_id);

CREATE UNIQUE INDEX one_active_login ON login_sessions (member_id) WHERE revoked_at IS NULL;

ALTER TABLE public.login_sessions ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.login_sessions FROM anon, authenticated;

CREATE TABLE recurring_tasks (
	id SERIAL NOT NULL, 
	member_id INTEGER NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	start_date VARCHAR(10) NOT NULL, 
	end_date VARCHAR(10), 
	PRIMARY KEY (id), 
	UNIQUE (id, member_id), 
	FOREIGN KEY(member_id) REFERENCES members (id)
);

ALTER TABLE public.recurring_tasks ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.recurring_tasks FROM anon, authenticated;

CREATE TABLE comments (
	id SERIAL NOT NULL, 
	diary_id INTEGER NOT NULL, 
	member_id INTEGER NOT NULL, 
	content VARCHAR(2000) NOT NULL, 
	created_at INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(diary_id) REFERENCES diaries (id) ON DELETE CASCADE, 
	FOREIGN KEY(member_id) REFERENCES members (id)
);

CREATE INDEX ix_comments_diary_id ON comments (diary_id);

ALTER TABLE public.comments ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.comments FROM anon, authenticated;

CREATE TABLE daily_tasks (
	id SERIAL NOT NULL, 
	member_id INTEGER NOT NULL, 
	recurring_task_id INTEGER, 
	task_date VARCHAR(10) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	completed BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (recurring_task_id, task_date), 
	FOREIGN KEY(recurring_task_id, member_id) REFERENCES recurring_tasks (id, member_id), 
	FOREIGN KEY(member_id) REFERENCES members (id)
);

CREATE INDEX ix_daily_tasks_member_id ON daily_tasks (member_id);

ALTER TABLE public.daily_tasks ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.daily_tasks FROM anon, authenticated;

CREATE TABLE refresh_tokens (
	id VARCHAR(36) NOT NULL, 
	session_id VARCHAR(36) NOT NULL, 
	digest VARCHAR(64) NOT NULL, 
	previous_id VARCHAR(36), 
	expires_at INTEGER NOT NULL, 
	rotated_at INTEGER, 
	retry_until INTEGER, 
	retry_payload TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES login_sessions (id), 
	UNIQUE (digest), 
	UNIQUE (previous_id), 
	FOREIGN KEY(previous_id) REFERENCES refresh_tokens (id)
);

CREATE INDEX ix_refresh_tokens_session_id ON refresh_tokens (session_id);

ALTER TABLE public.refresh_tokens ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.refresh_tokens FROM anon, authenticated;

COMMIT;

SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
