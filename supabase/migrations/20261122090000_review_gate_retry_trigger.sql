-- Applied to project ccdykioxztegxonuyvwb on 2026-11-22.
-- A reviewer verdict on a task decides its status: pass -> done;
-- fail/partial -> one retry (status pending, fix appended to instruction);
-- fail/partial after the retry -> blocked.

create or replace function public.apply_review_gate()
returns trigger
language plpgsql
as $$
declare
  v_verdict text;
begin
  v_verdict := lower(coalesce(new.review->>'verdict', ''));

  if v_verdict = 'pass' then
    new.status := 'done';
    insert into public.logs (task_id, event, detail)
    values (new.id, 'review_pass', jsonb_build_object('attempts', new.attempts));
  elsif old.attempts < 1 then
    new.status := 'pending';
    new.attempts := old.attempts + 1;
    new.not_before := null;
    new.instruction := old.instruction || E'\n\nFix from review: '
      || coalesce(nullif(new.review->>'fix', ''), 'address every unmet check in done_when');
    insert into public.logs (task_id, event, detail)
    values (new.id, 'review_retry', jsonb_build_object('verdict', v_verdict, 'fix', new.review->>'fix'));
  else
    new.status := 'blocked';
    new.error := 'review ' || coalesce(nullif(v_verdict, ''), 'unknown') || ' after retry';
    insert into public.logs (task_id, event, detail)
    values (new.id, 'review_blocked', jsonb_build_object('verdict', v_verdict));
  end if;

  return new;
end;
$$;

drop trigger if exists review_gate on public.tasks;

create trigger review_gate
before update of review on public.tasks
for each row
when (new.review is not null and new.review is distinct from old.review)
execute function public.apply_review_gate();
