-- Applied to project ccdykioxztegxonuyvwb on 2026-11-22.
-- Per-agent Gemini built-in tools and fallbacks.
-- Built-in tool names checked against the Gemini API docs: google_search, url_context, code_execution.
-- YouTube video analysis is passed as a file_data URI in the request, not as a tool.

update public.agents set capabilities = '{
  "provider": "gemini",
  "model": "gemini-3.1-flash-lite",
  "builtin_tools": ["google_search", "url_context"],
  "combine_with_function_tools": false,
  "video_input": "youtube_url",
  "fallback": {"on_tool_error": "plain_generation_marked_unverified", "on_rate_limit": "retry_with_backoff"}
}'::jsonb where id = 'leader';

update public.agents set capabilities = '{
  "provider": "gemini",
  "model": "gemini-3.1-flash-lite",
  "builtin_tools": ["google_search", "url_context"],
  "combine_with_function_tools": false,
  "video_input": "youtube_url",
  "fallback": {"on_tool_error": "plain_generation_marked_unverified", "on_rate_limit": "retry_with_backoff"}
}'::jsonb where id = 'researcher';

update public.agents set capabilities = '{
  "provider": "gemini",
  "model": "gemini-3.1-flash-lite",
  "builtin_tools": [],
  "combine_with_function_tools": false,
  "video_input": null,
  "fallback": {"on_rate_limit": "retry_with_backoff"}
}'::jsonb where id = 'writer';

update public.agents set capabilities = '{
  "provider": "gemini",
  "model": "gemini-3.1-flash-lite",
  "builtin_tools": ["code_execution", "url_context"],
  "combine_with_function_tools": false,
  "video_input": "youtube_url",
  "fallback": {"on_tool_error": "plain_generation_marked_unverified", "on_rate_limit": "retry_with_backoff"}
}'::jsonb where id = 'reviewer';
