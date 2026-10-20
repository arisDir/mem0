# mem0-self-improvement — Self-Improving Capture Skill

Turn corrections into durable memory. This skill teaches your assistant to record the developer's explicit corrections, unexpected command failures, and user feedback into Mem0 in a structured format — so a mistake fixed in one session is not repeated in the next.

> **Part of the Mem0 Skill Graph:**
> - Reference: [mem0](../mem0/SKILL.md) · [mem0-cli](../mem0-cli/SKILL.md) · [mem0-vercel-ai-sdk](../mem0-vercel-ai-sdk/SKILL.md)
> - Pipeline: [mem0-integrate](../mem0-integrate/SKILL.md) → [mem0-test-integration](../mem0-test-integration/SKILL.md) · [mem0-oss-to-platform](../mem0-oss-to-platform/SKILL.md)
> - Capture: **mem0-self-improvement** (this skill)

## What This Skill Does

- **Captures** three trigger types: an explicit behavior correction ("don't do X", "use Y instead"), an unexpected bash/script failure (wrong tool, missing script, unknown flag), and feedback on your output
- **Structures** every record with the three mandatory fields: `Trigger`, `Correction`, `Pattern-Key`
- **Stores** each record in Mem0 under one stable `agent_id` scope — verbatim (`infer=False`), deduped by Pattern-Key, with the project in metadata
- **Recalls** the pool at session start, before retrying a failed command, and when the user references the past

## Record Format

```text
Trigger: <the command or response that caused the issue>
Correction: <what the user desired, or what resolved the problem>
Pattern-Key: <concise kebab-case identifier for this recurring issue>
```

## When to Use

Trigger phrases:

- "Don't do X." / "Use Y instead." / "I told you to always ..."
- A command fails unexpectedly and the fix reveals the agent's wrong assumption
- "Too verbose." / "Show me the diff first." / any feedback on how the agent works

Do **not** use this skill for general SDK usage (install [`mem0`](../mem0/SKILL.md)), installing Mem0 into a project (use [`mem0-integrate`](../mem0-integrate/SKILL.md)), or ordinary debugging with no correction attached.

## Installation

### CLI (Claude Code, Codex, OpenCode, OpenClaw, or any tool that supports skills)

```bash
npx skills add https://github.com/mem0ai/mem0 --skill mem0-self-improvement
```

### Claude.ai

1. Download this `skills/mem0-self-improvement` folder as a ZIP
2. Go to **Settings > Capabilities > Skills**
3. Click **Upload skill** and select the ZIP

### Prerequisites

- A Mem0 Platform API key (`MEM0_API_KEY`, [get one](https://app.mem0.ai/dashboard/api-keys)), the `mem0` CLI, or the self-hosted OSS stack — any one channel the assistant can write to

## Links

- [Mem0 Platform Dashboard](https://app.mem0.ai)
- [Mem0 Documentation](https://docs.mem0.ai)

## License

Apache-2.0
