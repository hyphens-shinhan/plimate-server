# Seeding mentor data in Supabase

The mentor view in **hyphens-shinhan** (활성 멘티, 받은 요청, 메시지, **다가오는 미팅**, **총 멘토링 시간**, **응답률**) reads from the **same Supabase project** that **plimate-server** uses. If the DB has no mentoring requests, chat rooms, or meetings for the logged-in mentor, the mentor UI will be empty.

You can add **mock/seed data** via SQL so a test mentor account has something to show.

## Option 1: Run the seed script (recommended)

1. **Use the same Supabase project** as plimate-server (`SUPABASE_URL` in plimate-server env).
2. Ensure you have:
   - At least **one user with role = `MENTOR`** in `public.users`.  
     Create the user in **Supabase Dashboard → Authentication → Users**, then in SQL Editor run:
     ```sql
     UPDATE public.users SET role = 'MENTOR' WHERE id = '<that-user-uuid>';
     ```
   - At least **two YB/OB users** in `public.users` (you may already have these from real or test data).
3. Open **Supabase Dashboard → SQL Editor**, create a new query, paste the contents of **`scripts/seed_mentor_data.sql`**, and run it.

The script will:

- Create **`mentor_meetings`** table if it doesn’t exist (used for 다가오는 미팅 and 총 멘토링 시간).
- Pick the first user with `role = 'MENTOR'` and two non-mentor users.
- Insert **mentoring_requests**: 2 PENDING (받은 요청), 2 ACCEPTED (활성 멘티). **응답률** is computed from these (ACCEPTED + REJECTED / total).
- Insert **follows** (ACCEPTED, both directions) so the mentor can open DMs with those mentees.
- Create **one DM room** between the mentor and the first mentee with a few **chat_messages**.
- Insert **mentor_meetings**: 2 upcoming (다가오는 미팅) and 3 completed with duration (총 멘토링 시간).

After that, log in as the mentor in hyphens-shinhan; you should see active mentees, pending requests, one chat room with messages, **다가오는 미팅: 2**, **총 멘토링 시간: 3.3시간** (60+90+45 min), and **응답률** from your received requests.

## Option 2: Add data manually

If you prefer to insert data yourself or the script fails (e.g. missing tables/columns):

| What you need | Table(s) | Notes |
|---------------|----------|--------|
| Mentor user | `public.users` | `role = 'MENTOR'`. Create in Auth first, then ensure a row in `public.users` with that `id` and `role = 'MENTOR'`. |
| Mentee users | `public.users` | Existing YB/OB users. |
| 받은 요청 / 활성 멘티 | `public.mentoring_requests` | Columns: `mentee_id`, `mentor_id`, `message`, `status` (`PENDING` or `ACCEPTED`). |
| DMs visible to mentor | `public.follows`, `public.chat_rooms`, `public.chat_room_members`, `public.chat_messages` | Chats API requires **mutual follow** (two `follows` rows with `status = 'ACCEPTED'`: A→B and B→A). Then create a DM `chat_rooms` row, two `chat_room_members`, and some `chat_messages`. |

## Relation to existing YB/OB data

- **YB/OB students** are rows in `public.users` with `role` in `('YB', 'OB')` (or whatever values your app uses). They may already exist in the same Supabase project.
- The seed script **reuses those users** as mentees: it does not create new users, only new `mentoring_requests`, `follows`, and one DM room + messages.
- If you want a **specific user** to be the mentor, set their `role` to `'MENTOR'` in `public.users` before running the seed; the script picks the first MENTOR user.

## Running the script more than once

The script is written to avoid duplicates: it only inserts mentoring requests, follows, and the DM room when matching rows do not already exist. You can run it again; it will add data only for mentor/mentee pairs that don’t already have the same request/status or DM room.
