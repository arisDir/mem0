---
description: Copy all seven Mem0 skills into the global OpenCode skills directory and verify them
---

# Install the Mem0 skills into OpenCode

Follow these steps **in order** from the repository root.

Hard rules:

- **Never ask the user for anything.** Run the steps, then report the result.
- **Stop at the first failed check** and report what failed and the evidence.
- Safe to re-run: the install removes only the Mem0 skill copies it is about to
  replace, so running it again simply refreshes them.
- This command only copies files. It does not modify the repository and does
  not install `mem0ai`.

## 1. Locate the source skill folders

All shell below runs from the repository root:

```bash
cd "$(git rev-parse --show-toplevel)"
```

Define the list once and use it in every step below:

```bash
SKILLS="mem0 mem0-self-improvement"
```

Every source directory must exist with a root-level `SKILL.md`; stop and report
if any is missing:

```bash
for s in $SKILLS; do
  [ -f "skills/$s/SKILL.md" ] && echo "source ok: skills/$s/SKILL.md" \
    || { echo "MISSING: skills/$s/SKILL.md"; exit 1; }
done
```

## 2. Install (remove stale copies, then copy)

The destination is the **global** source, `~/.config/opencode/skills/`, so the
skills are available in every project. Point the copy at the parent directory
that contains the skill folders — never at a single skill folder, or OpenCode
derives the literal ID `SKILL`.

The removal pattern is intentional, so just drops stale or retired copies while 
leaving non-Mem0 skills in place.

```bash
mkdir -p ~/.config/opencode/skills
rm -rf "$HOME/.config/opencode/skills/"mem0*
for s in $SKILLS; do
  cp -R "skills/$s" "$HOME/.config/opencode/skills/$s"
  echo "installed: $s"
done
```

## 3. Verify

Each skill must have a `SKILL.md` at exactly this path — the ID is derived
from the directory name, case-sensitively (`mem0`, not `Mem0`):

```bash
for s in $SKILLS; do
  ls -l "$HOME/.config/opencode/skills/$s/SKILL.md" || exit 1
done
```

If `ls` fails for any skill, **stop** and report the error. Also check that
every `SKILL.md` has a `description` in its frontmatter — without one, the
skill never appears in the model's available-skills list:

```bash
for s in $SKILLS; do
  printf '%s: ' "$s"
  awk '/^description:/{print; exit}' "$HOME/.config/opencode/skills/$s/SKILL.md" \
    || echo "NO description frontmatter"
done
```

Finally, confirm the destination now holds exactly the seven Mem0 skills alongside
whatever else the user has installed:

```bash
ls -d "$HOME/.config/opencode/skills/"mem0* | sort
```

## 4. Final report

Give the user a short summary:

- **Installed:** all skills copied
  from `skills/` into `~/.config/opencode/skills/`.
- **Verified:** all seven `SKILL.md` files exist at the expected paths and all
  declare a `description`.
- **Next step:** restart OpenCode or start a new session so the configuration
  is re-read (if a running service caches config, run
  `opencode service restart`). Then confirm the IDs appear in the
  available-skills list, e.g. with `@mem0 explain how to add a memory`, or let
  the model load one via the `skill` tool with `{"id": "mem0"}`.
- **Refresh:** these are copies — after editing anything under `skills/`,
  re-run `/mem0-skill-setup` to pick up the changes.
