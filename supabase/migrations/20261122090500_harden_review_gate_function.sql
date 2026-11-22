-- Applied to project ccdykioxztegxonuyvwb on 2026-11-22.
-- Pins the search path and removes public execute permission on the trigger function.

alter function public.apply_review_gate() set search_path = public;
revoke execute on function public.apply_review_gate() from public, anon, authenticated;
