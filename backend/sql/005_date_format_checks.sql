-- Date strings must look like YYYY-MM-DD (API already validates; this guards direct SQL).
BEGIN;
ALTER TABLE public.diaries ADD CONSTRAINT diaries_diary_date_format CHECK (length(diary_date) = 10 AND substr(diary_date, 5, 1) = '-' AND substr(diary_date, 8, 1) = '-');
ALTER TABLE public.recurring_tasks ADD CONSTRAINT recurring_tasks_start_date_format CHECK (length(start_date) = 10 AND substr(start_date, 5, 1) = '-' AND substr(start_date, 8, 1) = '-');
ALTER TABLE public.recurring_tasks ADD CONSTRAINT recurring_tasks_end_date_format CHECK (end_date IS NULL OR (length(end_date) = 10 AND substr(end_date, 5, 1) = '-' AND substr(end_date, 8, 1) = '-'));
ALTER TABLE public.daily_tasks ADD CONSTRAINT daily_tasks_task_date_format CHECK (length(task_date) = 10 AND substr(task_date, 5, 1) = '-' AND substr(task_date, 8, 1) = '-');
COMMIT;
