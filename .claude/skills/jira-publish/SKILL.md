---
name: jira-publish
description: Publish an approved ticket manifest to Jira after a dry run, with a human confirmation (Stage 3, live mode)
disable-model-invocation: true
---

## Trigger

`/pm-publish <run-id>`

Only a human may trigger this skill. The model must never invoke it on its own. Nothing but `scripts/jira_publish.py` may write to Jira: no Jira MCP tool, no direct web call.

## Execution

1. Check the tickets approval (from the repo root):
```bash
.venv/bin/python scripts/check_approval.py runs/<run-id> tickets
```
It must print "approved". If not, stop and tell the human to run `/pm-approve tickets <run-id>` first.

2. Dry run first, through the `jira-publisher` agent:
```bash
.venv/bin/python scripts/jira_publish.py runs/<run-id>
```
Show the summary to the human in plain words.

3. Read `jira.mode` in `pm.config.yaml`. If it is `dry_run`, stop here and tell the human how to go live: see the README section "Going live with Jira" (set `jira.mode: publish`, `jira.site` and `jira.project_key`, and export `JIRA_EMAIL` and `JIRA_API_TOKEN`).

4. If `jira.mode` is `publish`:
   - Confirm `JIRA_EMAIL` and `JIRA_API_TOKEN` are set by checking only whether each one is non-empty. Never print them, never ask the human to paste them into the chat. If either is empty, stop and say which one is missing.
   - Run the live publish through the `jira-publisher` agent:
```bash
.venv/bin/python scripts/jira_publish.py runs/<run-id> --publish
```
   - Claude Code will show a confirmation prompt for this command. The human must accept it for the publish to run.

5. Report the result in plain words: the Jira keys created and updated (from `runs/<run-id>/tickets.published.json`) and the script's last line.

## On failure

- The script stops at the first ticket it cannot write and says which one failed. Keys already written stay in the manifest and `state.json`.
- Tell the human that running `/pm-publish <run-id>` again resumes where it stopped, without creating duplicates.
- Do not retry more than once yourself, and never edit `tickets.manifest.json` to fix it.

## Rules

- The script itself refuses without a valid tickets approval, without both keys (`jira.mode: publish` and `--publish`), with a placeholder site or project key, or without the two environment variables.
- Never run `scripts/approve.py` and never write under `runs/<run-id>/approvals/`.
- Never put credentials in a file, a command line, a log or the chat. They come only from the environment.
- Changing only the `jira_key` values after publishing does not make the tickets approval stale.
