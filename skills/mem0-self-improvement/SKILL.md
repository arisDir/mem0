---
name: mem0-self-improvement
description: >-
  Self-improving capture: records the developer's explicit corrections, unexpected command
  failures, and user feedback into mem0 as structured Trigger / Correction / Pattern-Key records,
  so the agent stops repeating mistakes across sessions. TRIGGER when: the user corrects the
  agent's behavior ("don't do X", "use Y instead", "always ..."), a bash command or script fails
  unexpectedly (command not found, missing script, wrong package manager, unknown flags), the
  user gives feedback on the agent's output, or a session starts and past corrections should be
  recalled before acting. DO NOT TRIGGER when: answering mem0 SDK usage questions (use `mem0`),
  installing or wiring mem0 into a project (use `mem0-integrate`), or debugging a defect with no
  correction or feedback attached — debug normally, capture only when a trigger fires.
license: Apache-2.0
metadata:
  author: mem0ai
  version: "0.1.0"
  category: ai-memory
  tags: "self-improvement, corrections, feedback, failure-capture, agent-memory"
  mem0_tested_versions: "mem0ai (PyPI) >=2.0.0,<3.0.0; mem0ai (npm) >=3.0.0,<4.0.0"
---

# Self-Improving Capture

## Overview

A correction that lives only in this conversation will be needed — and mishandled — again in the
next one. This skill turns corrections into durable mem0 memories that every later session reads
first.

The cycle:

1. **Capture** — a trigger fires (table below) → write one structured record to mem0.
2. **Recall** — at session start, before retrying, when the user references the past → read the
   pool back.
3. **Act** — follow the stored Corrections; update a record when the user changes their mind.

**Non-negotiable:** a capture only counts when the mem0 write returned a memory id. "I'll
remember" is not a capture, and a failed write is reported, never assumed to have worked.

## When to capture

| # | Trigger | Example |
|---|---------|---------|
| 1 | The user explicitly corrects your behavior | "Don't do X." / "Use Y instead." / "I told you to always ..." |
| 2 | A bash command or script fails unexpectedly | command not found, missing script, wrong package manager, flags that don't exist, tool not installed |
| 3 | The user gives feedback on your output | "Too verbose." / "Show me the diff first." / "Don't open PRs without asking." |

For trigger 2, capture once the fix is known — the record needs both the failure and its
resolution. A routine project bug the user already understands is not a trigger; an *unexpected*
failure caused by your wrong assumption is.

## The record format — all three fields, every time

```text
Trigger: <the command or response that caused the issue>
Correction: <what the user desired, or what resolved the problem>
Pattern-Key: <concise kebab-case identifier for this recurring issue>
```

- **Trigger** — quote the real command/error verbatim (trimmed to the essentials) or describe the
  user response that corrected you.
- **Correction** — phrased as an instruction a future session can follow without this
  conversation: what to do instead, or the fix that resolved the failure.
- **Pattern-Key** — 3–6 words, kebab-case, stable across recurrences. This is the dedupe and
  recall handle. Prefix project-specific keys with the project (`mem0-use-pnpm-not-npm`) so the
  same key never collides across repos.

Example — a record of the package-manager correction:

```text
Trigger: ran `npm install && npm run build` → `npm error Missing script: "build"`; repo is pnpm-only
Correction: use pnpm for every install/build in this repo; read package.json scripts before claiming one is missing
Pattern-Key: mem0-use-pnpm-not-npm
```

## Scope: one stable pool per agent

Every record is written under one fixed `agent_id` (e.g. `"opencode"`) — never a per-session id.
That fixed scope is what makes records readily available across all sessions: every later session
reads the same pool. Put the repo in `metadata.project` for context, and mirror the Pattern-Key
into `metadata.pattern_key` so it is filterable.

Two rules for every capture:

1. **Dedupe before writing.** Search the pool for the Pattern-Key. If it exists and the correction
   is unchanged, write nothing. If the correction *changed*, `update()` the existing record's text
   instead of adding a duplicate.
2. **Verify the write.** Confirm the call returned a memory id. A silent failure is a missed
   capture — report it.

## Write it — use the channel the environment has

Python (canonical; needs `MEM0_API_KEY` and `MEM0_BASE_URL` in the environment):

```python
from mem0 import MemoryClient
import os

client = MemoryClient(
    api_key=os.environ.get("MEM0_API_KEY"),
    host=os.environ.get("MEM0_BASE_URL"),
)  # reads MEM0_API_KEY and MEM0_BASE_URL from the environment
AGENT, PROJECT = "opencode", "mem0"

record = (
    "Trigger: ran `npm install && npm run build` → `npm error Missing script: \"build\"`; repo is pnpm-only\n"
    "Correction: use pnpm for every install/build in this repo; read package.json scripts before claiming one is missing\n"
    "Pattern-Key: mem0-use-pnpm-not-npm"
)

key = "mem0-use-pnpm-not-npm"
existing = client.search(key, filters={"agent_id": AGENT})
if not any(key in m["memory"] for m in existing.get("results", [])):
    client.add(
        record,
        agent_id=AGENT,
        metadata={"pattern_key": key, "project": PROJECT},
        infer=False,  # store verbatim — inference would rewrite the labeled fields
    )
```

CLI (language-agnostic):

```bash
mem0 add "$RECORD" --agent-id opencode \
  -m '{"pattern_key":"mem0-use-pnpm-not-npm","project":"mem0"}' --no-infer
```

For TypeScript call shapes, use the SDK skill (cross-references below): pass
`{ agentId, metadata, infer: false }` as the options object.

## Recall — read before you act

| Moment | Do |
|---|---|
| Session starts / first task in a repo | `client.get_all(filters={"agent_id": AGENT}, top_k=20)` — load the whole pool once |
| Before retrying a failed command or picking a tool | `client.search(<command or task>, filters={"agent_id": AGENT})` |
| The user references the past ("as I said", "I told you") | search before replying |

A fresh explicit instruction overrides a stored Correction — then update that record (same
Pattern-Key) so the next session sees the new rule.

## Red flags — the capture did not happen

| Red flag | Reality |
|---|---|
| "I'll remember that" / a mental note | Nothing crosses sessions except the mem0 write. |
| Freeform note missing Trigger, Correction, or Pattern-Key | Unstructured records can't be deduped or found; all three fields are mandatory. |
| A new scope (`user_id`, session id) per capture | The next session won't find it — scope is always the fixed `agent_id`. |
| Letting inference rewrite the record | Use `infer=False` / `--no-infer` so the labeled fields survive. |
| Adding a second record for a recurring key | Search first; `update()` if the correction changed. |
| Storing secrets (tokens, `.env` values) in a record | Store the lesson, never the credential. |
| A write that failed, left unreported | A failed capture must be reported, not assumed. |

## Cross-references

- SDK call patterns (Python + TypeScript, Platform + OSS): https://raw.githubusercontent.com/mem0ai/mem0/main/skills/mem0/SKILL.md
- CLI reference (`add`, `search`, `--no-infer`, metadata flags): https://raw.githubusercontent.com/mem0ai/mem0/main/skills/mem0-cli/SKILL.md
- Platform metadata filtering supports `eq`/`ne`/`contains`: https://docs.mem0.ai
