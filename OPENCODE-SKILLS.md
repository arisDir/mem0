# Installing the Mem0 Skills in OpenCode

How to make the six Mem0 skills in [`skills/`](./skills/) available to OpenCode, and how to refresh them after you edit the skills.

The skills were updated in commit `docs(skills): make all skills aware of the self-hosted OSS server` (all six now cover the self-hosted OSS server and the Python-only `ollama` reranker). Use the local install below to pick up those changes — the published `npx skills add` path still serves the upstream version until this branch is merged.

---

## 1. What you get

Each skill is a directory with a `SKILL.md` entry point. OpenCode derives the **skill ID** from the directory name (case-sensitive), not from the frontmatter `name`.

| ID | Directory | Covers |
|----|-----------|--------|
| `mem0` | `skills/mem0/` | Python + TypeScript SDKs (Platform + OSS), the self-hosted OSS REST server, framework integrations |
| `mem0-cli` | `skills/mem0-cli/` | `mem0` CLI (Node + Python) |
| `mem0-vercel-ai-sdk` | `skills/mem0-vercel-ai-sdk/` | `@mem0/vercel-ai-provider` |
| `mem0-integrate` | `skills/mem0-integrate/` | Wire Mem0 into a repo via a TDD pipeline (pipeline skill) |
| `mem0-test-integration` | `skills/mem0-test-integration/` | Verify an integration (pipeline skill) |
| `mem0-oss-to-platform` | `skills/mem0-oss-to-platform/` | Migrate OSS → hosted Platform (pipeline skill) |

The canonical self-hosted reference is [`skills/mem0/references/self-hosted-server.md`](./skills/mem0/references/self-hosted-server.md).

## 2. Prerequisites

- **OpenCode V2.** Nothing to compile — skills are plain Markdown.
- **Optional:** Python 3.10+ if you want the `mem0` skill's live doc-search tool (`skills/mem0/scripts/mem0_doc_search.py`). It uses only the standard library, so no `pip install` is required.
- The skills reference the Mem0 SDKs and API in their examples, but installing them does not install `mem0ai`.

## 3. How OpenCode discovers skills

OpenCode searches for a directory that contains either root-level `*.md` skills or nested `SKILL.md` files. Relevant sources:

| Scope | Locations |
|-------|-----------|
| Global | `~/.config/opencode/skills` |
| Global compatibility | `~/.claude/skills`, `~/.agents/skills` |
| Project | `.opencode/skills` (searched from the project root toward the current directory) |
| Project compatibility | `.claude/skills`, `.agents/skills` |
| Explicit | any path listed in the `skills` array of an `opencode.json(c)` |

Point a source at the **parent** directory that contains the skill folders — not at a single skill folder. A bare `SKILL.md` at the root of a source gets the literal ID `SKILL`, so a source of `skills/mem0` would produce `SKILL`, while a source of `skills/` produces `mem0`.

> This repo's `/home/aris/projects/mem0/opencode.json` already declares `"skills": [".openwork/skills"]`, but `.openwork/skills/` does not exist yet. That is the repo-local install target (Option B).

## 4. Option A — Global install (recommended)

Symlink the skill folders into the global source so they are available in every project and always reflect your edits to `skills/`:

```bash
mkdir -p ~/.config/opencode/skills
for s in mem0 mem0-cli mem0-vercel-ai-sdk mem0-integrate mem0-test-integration mem0-oss-to-platform; do
  ln -sfn "/home/aris/projects/mem0/skills/$s" "$HOME/.config/opencode/skills/$s"
done
ls -l ~/.config/opencode/skills
```

Symlinks mean there is nothing to re-copy when you edit a skill file.

## 5. Option B — Repo-local install

Use this if you only want the skills while working inside the mem0 repo. It satisfies the `"skills": [".openwork/skills"]` entry already present in `opencode.json`:

```bash
mkdir -p /home/aris/projects/mem0/.openwork/skills
for s in mem0 mem0-cli mem0-vercel-ai-sdk mem0-integrate mem0-test-integration mem0-oss-to-platform; do
  ln -sfn "/home/aris/projects/mem0/skills/$s" "/home/aris/projects/mem0/.openwork/skills/$s"
done
```

The `skills` path is resolved from the active OpenCode working directory, so open OpenCode in `/home/aris/projects/mem0` (or a worktree of it).

## 6. Option C — Point config at the skills directory

Add the directory to any `opencode.json(c)` instead of symlinking. Global example (`~/.config/opencode/opencode.json`):

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "skills": ["/home/aris/projects/mem0/skills"]
}
```

Caveat: this source root also contains `README.md` and `AGENTS.md`. They register as flat skills (`README`, `AGENTS`) but have no `description`, so they are never advertised to the model. Symlinking (Options A/B) avoids this entirely.

## 7. Option D — Published install (upstream only)

For the released versions:

```bash
npx skills add https://github.com/mem0ai/mem0 --skill mem0
```

This pulls from upstream `main`, so it will **not** include the local modifications until the branch is merged (or you point it at your own fork/branch). Prefer Option A/B while developing the skills.

## 8. Verify it works

1. Restart OpenCode so configuration is re-read, or start a new session. If a running service caches config, run `opencode service restart`.
2. The six IDs above should now appear in the model's available-skills list.
3. Load one explicitly by mentioning it in your prompt, e.g. `@mem0 explain how to add a memory`, or let the model load it via the `skill` tool with `{"id": "mem0"}`.
4. Smoke test: ask something that should trigger the skill, e.g. *"Using mem0, add a memory for user alice."* Expect the `mem0` skill to be selected.

Quick check that the source is mounted correctly:

```bash
ls -l ~/.config/opencode/skills/mem0/SKILL.md   # Option A
ls -l /home/aris/projects/mem0/.openwork/skills/mem0/SKILL.md   # Option B
```

## 9. Refresh after future edits

- **Options A/B (symlinks):** edit files under `skills/` and the changes are live. Start a new session so the updated `SKILL.md` is re-read.
- **Option C (config path):** same — the directory is read directly.
- **Option D (`npx skills add`):** re-run the command, or bump the skill's `metadata.version` and reinstall.

## 10. Troubleshooting

- **A skill is missing.** Confirm the file is either a root-level `*.md` in a source, or named exactly `SKILL.md` inside a subdirectory of a source.
- **Wrong skill loads.** IDs are path-derived and case-sensitive (`mem0`, not `Mem0`); the frontmatter `name` is only a label.
- **A skill never appears for the model.** It needs a `description` in frontmatter. Also check that `metadata.opencode/autoinvoke` is not `false`.
- **Deduplication.** If two sources define the same ID, the later/higher-precedence source wins (project beats global; explicit `skills` entries beat both).
- **Permissions.** Loading a skill is governed by the `skill` action. If a `deny` rule hides the mem0 skills, allow them in the V2 `permissions` array:

  ```jsonc
  {
    "permissions": [
      { "action": "skill", "resource": "mem0*", "effect": "allow" }
    ]
  }
  ```

- **`${CLAUDE_SKILL_DIR}` in the `mem0` skill.** The doc-search examples use this Claude Code variable. In OpenCode, use the skill's reported base directory instead, e.g. `python <skill-dir>/scripts/mem0_doc_search.py --query "graph memory"`.

## 11. Notes

- The skills describe three ways to run mem0: hosted Platform (`MemoryClient`, `/v1`,`/v3`, `Authorization: Token`), the in-process OSS `Memory` class, and the self-hosted OSS REST server (`server/`, unversioned paths, `X-API-Key`). The self-hosted reference is the place to start for the server in this repo.
- Installing skills does not modify the repo; it only registers the existing `skills/` files with OpenCode.
