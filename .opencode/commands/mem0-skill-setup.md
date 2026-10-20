---
description: Copy the mem0 and mem0-cli skills into the global OpenCode skills directory and verify them
---

# Install the `mem0` and `mem0-cli` skills into OpenCode

Follow these steps **in order** from the repository root. This is the local
install from `OPENCODE-SKILLS.md` (sections 4–6), scoped to the two skills:
`mem0` and `mem0-cli`. The other four Mem0 skills are **not** touched.

Hard rules:

- **Never ask the user for anything.** Run the steps, then report the result.
- **Stop at the first failed check** and report what failed and the evidence.
- Safe to re-run: the install removes only the two stale copies it is about to
  replace, so running it again simply refreshes them.
- This command only copies files. It does not modify the repository and does
  not install `mem0ai`.

## 1. Locate the source skill folders

All shell below runs from the repository root:

```bash
cd "$(git rev-parse --show-toplevel)"
```

Both source directories must exist; stop and report if either does not:

```bash
for s in mem0 mem0-cli; do
  [ -f "skills/$s/SKILL.md" ] && echo "source ok: skills/$s/SKILL.md" \
    || { echo "MISSING: skills/$s/SKILL.md"; exit 1; }
done
```

## 2. Install (remove stale copies, then copy)

The destination is the **global** source, `~/.config/opencode/skills/`, so the
skills are available in every project. Point the copy at the parent directory
that contains the skill folders — never at a single skill folder, or OpenCode
derives the literal ID `SKILL`.

Only `mem0` and `mem0-cli` are removed first. Do **not** use a `mem0*` glob
here: it would delete the other four Mem0 skills the user may have installed.

```bash
mkdir -p ~/.config/opencode/skills
for s in mem0 mem0-cli; do
  rm -rf "$HOME/.config/opencode/skills/$s"
  cp -R "skills/$s" "$HOME/.config/opencode/skills/$s"
  echo "installed: $s"
done
```

## 3. Verify

Each skill must have a `SKILL.md` at exactly this path — the ID is derived
from the directory name, case-sensitively (`mem0`, not `Mem0`):

```bash
for s in mem0 mem0-cli; do
  ls -l "$HOME/.config/opencode/skills/$s/SKILL.md"
done
```

If `ls` fails for either skill, **stop** and report the error. Also check that
both `SKILL.md` files have a `description` in their frontmatter — without one,
the skill never appears in the model's available-skills list:

```bash
for s in mem0 mem0-cli; do
  printf '%s: ' "$s"
  awk '/^description:/{print; exit}' "$HOME/.config/opencode/skills/$s/SKILL.md" \
    || echo "NO description frontmatter"
done
```

## 4. Final report

Give the user a short summary:

- **Installed:** `mem0` and `mem0-cli`, copied from `skills/` into
  `~/.config/opencode/skills/`.
- **Verified:** both `SKILL.md` files exist at the expected paths and both
  declare a `description`.
- **Next step:** restart OpenCode or start a new session so the configuration
  is re-read (if a running service caches config, run
  `opencode service restart`). Then confirm the two IDs appear in the
  available-skills list, e.g. with `@mem0 explain how to add a memory`.
- **Refresh:** these are copies — after editing anything under `skills/`,
  re-run `/mem0-skill-setup` to pick up the changes.
