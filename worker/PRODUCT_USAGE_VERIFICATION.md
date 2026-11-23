# Product usage verification (10 real users)

AI House treats ten-user validation as a real adoption milestone, not a marketing claim.

## What counts

The verification task expects an actual production analytics export at:

`reports/product-usage-events.jsonl`

The path is relative to the current business workspace. JSON Lines is supported (one JSON object per line); a JSON array or an object containing an `events`, `results`, or `data` array is also supported.

Example event:

```json
{"user_id":"sha256:stable-pseudonymous-user-id","event_name":"core_action","environment":"production","timestamp":"2026-11-23T10:30:00Z","is_test":false}
```

Allowed qualifying event names include `activation`, `core_action`, `completed_workflow`, `product_use`, `feature_used`, `core_feature_used`, and `key_action`.

The verifier counts distinct stable user IDs that performed a qualifying event in the last 30 days. Repeated actions by the same user do not increase the user count.

## Exclusions

- Owner and internal accounts (set `is_owner` or `is_internal`, or list their stable IDs in `workspace/.ai-house/owner_user_ids.json`)
- Test accounts and synthetic events (`is_test` / `test`)
- Bots (`is_bot` / `bot`)
- Development/staging events (the event must say `environment: production` or `env: prod`)
- Page views, impressions, downloads, marketing clicks, and outreach are not product usage

The owner ID file may be a JSON array of stable IDs or an object such as:

```json
{"user_ids":["sha256:owner-pseudonymous-id"]}
```

Use stable pseudonymous IDs, not email addresses or names. The verification report stores short SHA-256 fingerprints rather than raw IDs.

## Honest status

The Leader's review includes a deterministic usage report. If fewer than ten distinct production users are evidenced, the task remains pending/improving and cannot be approved as having reached the milestone. The report is a count of distinct production user accounts; it cannot prove that each account is a separate human being.

AI House cannot magically observe an app's analytics. The product must instrument core actions and provide a genuine analytics export (from its database or analytics provider). Without that export, the milestone stays pending rather than being guessed.
