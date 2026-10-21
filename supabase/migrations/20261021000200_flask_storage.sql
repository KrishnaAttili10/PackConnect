-- Existing Supabase tables may have required an Auth UUID for legacy messages.
-- Flask keeps legacy messages for import only; new chat uses chat_messages.
BEGIN;
ALTER TABLE public.messages ALTER COLUMN sender_user_id DROP NOT NULL;

INSERT INTO public.notifications (user_id, actor_id, request_id, kind, event_key)
SELECT recipient_id, sender_id, id, 'request_received', 'request:' || id
FROM public.advice_requests WHERE status = 'pending'
ON CONFLICT (event_key) DO NOTHING;
INSERT INTO public.notifications (user_id, actor_id, request_id, kind, event_key)
SELECT sender_id, recipient_id, id, status, 'decision:' || id
FROM public.advice_requests WHERE status IN ('accepted', 'declined')
ON CONFLICT (event_key) DO NOTHING;
COMMIT;
