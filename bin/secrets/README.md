# bin/secrets/

Credentials and webhook URLs. Gitignored — never committed.

## Files that go here

| File | What it holds |
|---|---|
| `slack-webhook.txt` | Slack Incoming Webhook URL for `notify_slack.py`. Get from api.slack.com/apps → Incoming Webhooks. |
| `keyring.env` | The agent keyring — API keys for `bin/api.py` / `bin/gen_image.py` (YouTube, Gemini, Sketchfab, Resend, Supabase, ...). Copy `keyring.env.template` and fill in what you have. Keys are injected at request time and redacted from all output; agents run `api.py`, never read this file. |

## Setup

1. Create `slack-webhook.txt` and paste your webhook URL (one line, no trailing newline)
2. Or set the `SLACK_WEBHOOK_URL` environment variable — scripts check this first and fall back to the file

Scripts that use secrets gracefully no-op if the file is missing — they won't crash, they just won't deliver notifications.
