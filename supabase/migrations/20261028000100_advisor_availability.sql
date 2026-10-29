BEGIN;

ALTER TABLE public.students ADD COLUMN IF NOT EXISTS max_open_requests integer DEFAULT 5
    CHECK (max_open_requests BETWEEN 1 AND 100);
ALTER TABLE public.students ADD COLUMN IF NOT EXISTS pause_until date;

ALTER TABLE public.advice_requests DROP CONSTRAINT IF EXISTS advice_requests_status_check;
ALTER TABLE public.advice_requests ADD CONSTRAINT advice_requests_status_check
    CHECK (status IN ('pending', 'accepted', 'declined', 'completed'));

CREATE INDEX IF NOT EXISTS advisor_open_requests ON public.advice_requests (recipient_id)
    WHERE status IN ('pending', 'accepted');

NOTIFY pgrst, 'reload schema';
COMMIT;
