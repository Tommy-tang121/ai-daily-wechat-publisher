# DeepSeek JSON Reliable Output Design

## Goal

Replace the current Agnes model service with DeepSeek for the daily rewrite
step, while preserving the existing source collection, full-day article
requirement, WeChat publishing flow, and strict no-partial-publish rule.

## Decision

Use DeepSeek `deepseek-v4-flash` through its OpenAI-compatible endpoint
`https://api.deepseek.com`.

For this structured daily task, each DeepSeek request must:

- disable thinking with `thinking: {"type": "disabled"}`;
- request a JSON object with `response_format: {"type": "json_object"}`;
- retain the existing `max_tokens: 8000`, complete-item validation, and one
  same-input retry.

The existing prompt already names JSON and provides a JSON shape. The local
parser remains the final gate: malformed, empty, partial, or missing-item
responses must never be published to WeChat.

## Configuration and Secret Handling

Only the locally ignored root `.env` changes:

- `LLM_API_KEY` becomes the user-provided DeepSeek API key;
- `LLM_BASE_URL` becomes `https://api.deepseek.com`;
- `LLM_MODEL` becomes `deepseek-v4-flash`.

The API key must not appear in source files, documentation, tests, logs, or
Git commits.

## Scope

Change the existing OpenAI-compatible request adapter only enough to send the
two DeepSeek reliability parameters when the configured endpoint is DeepSeek.
All non-DeepSeek request behavior remains unchanged.

No change is made to scraping, article layout, cover generation, WeChat
credentials, scheduling time, or publishing semantics.

## Verification

1. Check that the configured DeepSeek endpoint accepts the key without
   printing it.
2. Send a short JSON-only request and verify a parseable final `content`.
3. Build the complete current-day article in preview-only mode and verify all
   items, opening, closing, and local source links are present.
4. Trigger the existing Windows task once only after the preview succeeds.
5. Confirm that a successful task reaches the WeChat draft stage; if it fails,
   report a classified safe error and do not republish.
