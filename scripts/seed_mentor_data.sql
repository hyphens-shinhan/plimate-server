-- Seed mentor-related data for plimate-server Supabase
-- Use this so the mentor view (hyphens-shinhan) has something to show:
--   - 활성 멘티 (accepted mentoring requests)
--   - 받은 요청 (pending requests)
--   - 메시지 (DM rooms with messages)
--   - 다가오는 미팅, 총 멘토링 시간, 응답률 (via mentor_meetings + mentoring_requests)
--
-- Prerequisites:
--   1. Same Supabase project that plimate-server uses (SUPABASE_URL).
--   2. At least one user with role = 'MENTOR' in public.users (create in Auth first, then set role).
--   3. At least 2 YB/OB users in public.users (you may already have these).
--
-- Run in: Supabase Dashboard → SQL Editor → New query → paste → Run.

-- ============================================
-- Table for mentor stats (다가오는 미팅, 총 멘토링 시간)
-- ============================================
CREATE TABLE IF NOT EXISTS public.mentor_meetings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mentor_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  mentee_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
  completed_at TIMESTAMP WITH TIME ZONE,
  duration_minutes INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mentor_meetings_mentor_id ON public.mentor_meetings(mentor_id);
CREATE INDEX IF NOT EXISTS idx_mentor_meetings_scheduled_at ON public.mentor_meetings(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_mentor_meetings_completed_at ON public.mentor_meetings(completed_at);

-- ============================================
-- Add date/time and meeting method to mentoring_requests (if not present)
-- ============================================
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'mentoring_requests') THEN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'mentoring_requests' AND column_name = 'preferred_date') THEN
      ALTER TABLE public.mentoring_requests ADD COLUMN preferred_date DATE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'mentoring_requests' AND column_name = 'preferred_time') THEN
      ALTER TABLE public.mentoring_requests ADD COLUMN preferred_time TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'mentoring_requests' AND column_name = 'preferred_meeting_method') THEN
      ALTER TABLE public.mentoring_requests ADD COLUMN preferred_meeting_method TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'mentoring_requests' AND column_name = 'scheduled_at') THEN
      ALTER TABLE public.mentoring_requests ADD COLUMN scheduled_at TIMESTAMP WITH TIME ZONE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'mentoring_requests' AND column_name = 'meeting_method') THEN
      ALTER TABLE public.mentoring_requests ADD COLUMN meeting_method TEXT;
    END IF;
  END IF;
END $$;

DO $$
DECLARE
  v_mentor_id     UUID;
  v_mentee1_id    UUID;
  v_mentee2_id    UUID;
  v_room_id       UUID;
BEGIN
  -- 1) Pick first mentor
  SELECT id INTO v_mentor_id
  FROM public.users
  WHERE role = 'MENTOR'
  LIMIT 1;

  IF v_mentor_id IS NULL THEN
    RAISE NOTICE 'No user with role MENTOR found. Create one in Auth, then: UPDATE public.users SET role = ''MENTOR'' WHERE id = ''<user_id>'';';
    RETURN;
  END IF;

  -- 2) Pick two non-mentor users as mentees (not already in a mentoring request with this mentor)
  SELECT id INTO v_mentee1_id
  FROM public.users u
  WHERE u.role IS DISTINCT FROM 'MENTOR'
    AND u.id != v_mentor_id
    AND NOT EXISTS (SELECT 1 FROM public.mentoring_requests mr WHERE mr.mentor_id = v_mentor_id AND mr.mentee_id = u.id)
  LIMIT 1;

  SELECT id INTO v_mentee2_id
  FROM public.users u
  WHERE u.role IS DISTINCT FROM 'MENTOR'
    AND u.id != v_mentor_id
    AND u.id != v_mentee1_id
    AND NOT EXISTS (SELECT 1 FROM public.mentoring_requests mr WHERE mr.mentor_id = v_mentor_id AND mr.mentee_id = u.id)
  LIMIT 1;

  IF v_mentee1_id IS NULL OR v_mentee2_id IS NULL THEN
    RAISE NOTICE 'Need at least 2 YB/OB users in public.users that are not already in a mentoring request with this mentor.';
    RETURN;
  END IF;

  -- 3) Mentoring requests: 2 PENDING (받은 요청), 2 ACCEPTED (활성 멘티), with date/time and meeting method
  INSERT INTO public.mentoring_requests (mentee_id, mentor_id, message, status, created_at, preferred_date, preferred_time, preferred_meeting_method)
  SELECT v_mentee1_id, v_mentor_id, '진로와 학업 설계에 대해 멘토링 받고 싶습니다.', 'PENDING', NOW() - INTERVAL '2 days', (CURRENT_DATE + INTERVAL '5 days')::date, '14:00', 'ONLINE'
  WHERE NOT EXISTS (SELECT 1 FROM public.mentoring_requests WHERE mentee_id = v_mentee1_id AND mentor_id = v_mentor_id AND status = 'PENDING');

  INSERT INTO public.mentoring_requests (mentee_id, mentor_id, message, status, created_at, preferred_date, preferred_time, preferred_meeting_method)
  SELECT v_mentee2_id, v_mentor_id, '취업 준비와 이력서 피드백 부탁드립니다.', 'PENDING', NOW() - INTERVAL '1 day', (CURRENT_DATE + INTERVAL '7 days')::date, '19:30', 'OFFLINE'
  WHERE NOT EXISTS (SELECT 1 FROM public.mentoring_requests WHERE mentee_id = v_mentee2_id AND mentor_id = v_mentor_id AND status = 'PENDING');

  INSERT INTO public.mentoring_requests (mentee_id, mentor_id, message, status, created_at, preferred_date, preferred_time, preferred_meeting_method, scheduled_at, meeting_method)
  SELECT v_mentee1_id, v_mentor_id, '커리어 상담 요청드립니다.', 'ACCEPTED', NOW() - INTERVAL '5 days', (CURRENT_DATE - INTERVAL '3 days')::date, '14:00', 'ONLINE', (NOW() + INTERVAL '3 days'), 'ONLINE'
  WHERE NOT EXISTS (SELECT 1 FROM public.mentoring_requests WHERE mentee_id = v_mentee1_id AND mentor_id = v_mentor_id AND status = 'ACCEPTED');

  INSERT INTO public.mentoring_requests (mentee_id, mentor_id, message, status, created_at, preferred_date, preferred_time, preferred_meeting_method, scheduled_at, meeting_method)
  SELECT v_mentee2_id, v_mentor_id, '리더십 개발 멘토링 요청합니다.', 'ACCEPTED', NOW() - INTERVAL '3 days', (CURRENT_DATE - INTERVAL '1 day')::date, '19:00', 'FLEXIBLE', (NOW() + INTERVAL '7 days'), 'ONLINE'
  WHERE NOT EXISTS (SELECT 1 FROM public.mentoring_requests WHERE mentee_id = v_mentee2_id AND mentor_id = v_mentor_id AND status = 'ACCEPTED');

  -- 4) Mutual follows (ACCEPTED) so mentor and mentees can DM
  INSERT INTO public.follows (requester_id, receiver_id, status)
  SELECT v_mentor_id, v_mentee1_id, 'ACCEPTED'
  WHERE NOT EXISTS (SELECT 1 FROM public.follows WHERE requester_id = v_mentor_id AND receiver_id = v_mentee1_id);
  INSERT INTO public.follows (requester_id, receiver_id, status)
  SELECT v_mentee1_id, v_mentor_id, 'ACCEPTED'
  WHERE NOT EXISTS (SELECT 1 FROM public.follows WHERE requester_id = v_mentee1_id AND receiver_id = v_mentor_id);
  INSERT INTO public.follows (requester_id, receiver_id, status)
  SELECT v_mentor_id, v_mentee2_id, 'ACCEPTED'
  WHERE NOT EXISTS (SELECT 1 FROM public.follows WHERE requester_id = v_mentor_id AND receiver_id = v_mentee2_id);
  INSERT INTO public.follows (requester_id, receiver_id, status)
  SELECT v_mentee2_id, v_mentor_id, 'ACCEPTED'
  WHERE NOT EXISTS (SELECT 1 FROM public.follows WHERE requester_id = v_mentee2_id AND receiver_id = v_mentor_id);

  -- 5) One DM room: mentor + first mentee, with a few messages (only if room doesn't exist)
  IF NOT EXISTS (
    SELECT 1 FROM public.chat_room_members m1
    JOIN public.chat_room_members m2 ON m1.room_id = m2.room_id AND m1.user_id < m2.user_id
    JOIN public.chat_rooms r ON r.id = m1.room_id AND r.type = 'DM'
    WHERE m1.user_id = v_mentor_id AND m2.user_id = v_mentee1_id
  ) THEN
    INSERT INTO public.chat_rooms (id, type, created_by, created_at)
    VALUES (gen_random_uuid(), 'DM', v_mentor_id, NOW())
    RETURNING id INTO v_room_id;

    INSERT INTO public.chat_room_members (room_id, user_id)
    VALUES (v_room_id, v_mentor_id), (v_room_id, v_mentee1_id);

    INSERT INTO public.chat_messages (sender_id, room_id, message, file_urls, sent_at)
    VALUES
      (v_mentee1_id, v_room_id, '안녕하세요, 멘토링 요청 드렸던 학생입니다.', ARRAY[]::text[], NOW() - INTERVAL '4 days'),
      (v_mentor_id, v_room_id, '안녕하세요. 편하실 때 미팅 잡아요.', ARRAY[]::text[], NOW() - INTERVAL '4 days' + INTERVAL '1 hour'),
      (v_mentee1_id, v_room_id, '다음 주 화요일 오후 2시 가능하실까요?', ARRAY[]::text[], NOW() - INTERVAL '3 days');

    RAISE NOTICE 'DM room created: %', v_room_id;
  END IF;

  -- 6) Mentor meetings: upcoming (다가오는 미팅) + completed (총 멘토링 시간). Seed only if none exist.
  IF to_regclass('public.mentor_meetings') IS NOT NULL THEN
    IF (SELECT COUNT(*) FROM public.mentor_meetings WHERE mentor_id = v_mentor_id) = 0 THEN
      -- Upcoming: 2 meetings in the future (no completed_at)
      INSERT INTO public.mentor_meetings (mentor_id, mentee_id, scheduled_at, completed_at, duration_minutes)
      VALUES
        (v_mentor_id, v_mentee1_id, NOW() + INTERVAL '3 days', NULL, 0),
        (v_mentor_id, v_mentee2_id, NOW() + INTERVAL '7 days', NULL, 0);
      -- Completed: past meetings with duration (총 멘토링 시간 = 60+90+45 = 195 min ≈ 3.25 h)
      INSERT INTO public.mentor_meetings (mentor_id, mentee_id, scheduled_at, completed_at, duration_minutes)
      VALUES
        (v_mentor_id, v_mentee1_id, NOW() - INTERVAL '10 days', NOW() - INTERVAL '10 days', 60),
        (v_mentor_id, v_mentee1_id, NOW() - INTERVAL '20 days', NOW() - INTERVAL '20 days', 90),
        (v_mentor_id, v_mentee2_id, NOW() - INTERVAL '5 days', NOW() - INTERVAL '5 days', 45);
      RAISE NOTICE 'Mentor meetings seeded (2 upcoming, 3 completed).';
    END IF;
  END IF;

  RAISE NOTICE 'Seed done. Mentor: %, Mentees: %, %', v_mentor_id, v_mentee1_id, v_mentee2_id;
END $$;
