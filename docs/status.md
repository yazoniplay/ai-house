# Status (2026-11-22)

## Done
- Schema live: rooms, agents, tasks, approvals, logs, lessons.
- Worker functions: claim_next_task, decide_approval.
- Review gate: pass -> done; fail/partial -> one retry -> blocked. Tested on throwaway tasks.
- Per-agent Gemini capabilities stored in agents.capabilities.
- Smoke test ran before the review gate; those two worker tasks have review = null.

## Not done
- Worker code: nothing yet that calls Gemini or claims tasks.
- Live Gemini test: no API key used yet.
- Approvals and lessons are empty.

## Open decisions
- Free-tier Gemini data may be used by Google to improve products. Decide what business data may go through it.
- Leader quality: currently Flash Lite. Decide whether the leader needs a stronger model.
- Token Harbor provider: not added.
- Built-in tools combined with function tools in one request: Google's docs disagree. Kept off.

## To check
- Security: no RLS policies exist. claim_next_task and decide_approval are SECURITY DEFINER and may be callable through the public API. Not verified; run Supabase advisors.

## Next
1. Confirm the security check.
2. Write the worker: claim task, call Gemini with the agent's capabilities, write output, set review.
3. Run the smoke test with real calls and record results in docs/.
