---
description: Cut a release — pre-flight, draft changelog, get approval, tag and push
---

You are preparing a new release of folio.
folio is a Python CLI tool distributed via GitHub Releases.
A version tag push creates a GitHub Release with an auto-generated source tarball.
Users install via `uv tool install git+https://github.com/RKelln/folio@v{version}`
or clone and `uv tool install --editable .`.

Your job is to prepare the changelog, get human approval, then tag and push.

## Arguments

Arguments provided: $ARGUMENTS

Parse as: `[version] [description]`

- `$1` — the new version (e.g. `v0.1.0` or `0.1.0`). Required.
  Normalise: always store as `v{MAJOR}.{MINOR}.{PATCH}`. Reject non-semver.
- `$2` — a short one-line release title (e.g. `"Initial public release"`).
  Optional — draft one from the commit history if omitted and confirm with user.

If no arguments are provided, read the latest git tag and suggest the next
minor bump as default, then ask the user.

---

## Step 1 — Validate version and read current state

Run in parallel:

```bash
# Latest release tag (empty if no releases yet)
git describe --tags --abbrev=0 2>/dev/null || echo "(no prior releases)"

# Commits since last tag (or all commits if no tag)
git log $(git describe --tags --abbrev=0 2>/dev/null || git rev-list --max-parents=0 HEAD)..HEAD --oneline

# Current branch and working tree state
git status --short

# Current version in pyproject.toml
grep '^version' pyproject.toml

# Current __version__ in __init__.py (must match pyproject.toml)
grep '__version__' src/folio/__init__.py
```

Display to the user:

```
Previous release: v{prev}  (or "none — this is the first release")
New release:      v{new}
Commits since:    {N} commits
```

If `v{new}` is not strictly greater than `v{prev}` (semver compare), warn and
ask for confirmation before continuing.

---

## Step 2 — Pre-flight checks

Run each check. If any fails, stop and report the failure clearly before
asking whether to continue.

```bash
# 1. On main branch
git branch --show-current

# 2. Clean working tree (nothing uncommitted)
git status --porcelain

# 3. Up to date with origin
git fetch origin main --dry-run 2>&1

# 4. Tests pass
uv run pytest tests/ --ignore=tests/test_frontmatter.py -q

# 5. Lint passes (warnings OK, no errors)
uv run ruff check src/

# 6. Package builds cleanly
uv build 2>&1
```

Do not proceed past Step 2 if any pre-flight check fails.

---

## Step 3 — Gather git history for release notes

Run in parallel to collect raw material:

```bash
# Full oneline log since last tag (or all commits for first release)
PREV=$(git describe --tags --abbrev=0 2>/dev/null || git rev-list --max-parents=0 HEAD)
git log ${PREV}..HEAD --oneline

# Detailed log with commit bodies
git log ${PREV}..HEAD --format="### %s%n%n%b"

# File change summary
git diff ${PREV}..HEAD --stat
```

---

## Step 4 — Draft release notes

Analyse the git history from Step 3 and draft structured release notes using
Keep a Changelog format. Map conventional commit types to sections:

- `feat:` / `feat(…):` → **Added**
- `fix:` / `fix(…):` → **Fixed**
- `refactor:` / `refactor(…):` → **Changed**
- `docs:` / `docs(…):` → **Documentation** (include only if user-visible)
- `ci:` / `chore:` / `test:` → **Infrastructure** (include sparingly)

Template:

```markdown
## [v{new}] — {description} — {YYYY-MM-DD}

{1-2 sentence summary of what this release represents}

### Added
- {feature bullets — be specific about commands, flags, and behaviors}

### Fixed
- {bug fix bullets}

### Changed
- {behaviour changes, refactors visible to users}

### Infrastructure
- {CI, build tooling, internal changes — omit if nothing notable}
```

Guidelines:
- Group related commits into single bullets rather than listing every commit
- Name specific commands, flags, and files — avoid vague "various improvements"
- If no `$2` description was given, draft a title from the overall theme and
  present it with the notes for the user to approve
- For the first release with many commits, focus on end-user features (commands,
  install methods, agent workflow) rather than internal implementation steps

Write the full draft to: `dist/RELEASE_NOTES_DRAFT.md` (create `dist/` if needed).

Present a preview to the user:

```
── Draft release notes written to dist/RELEASE_NOTES_DRAFT.md ──

## [v{new}] — {description}

{first 4-5 bullet points…}

(full notes in dist/RELEASE_NOTES_DRAFT.md)
```

Ask: **"Edit the file and let me know when ready, or approve as-is?"**

Wait for the user to respond:
- **Approve** ("looks good", "ok", "lgtm", "approve") — read the file back and use as-is.
- **Edit** — wait for them to say they're done, then read the file back and confirm.
- **Inline corrections** — apply changes to the draft file, show the updated version, and ask again.

Before proceeding, proofread the approved notes for typos (command names, flag
names, URLs, repo paths are common spots). Fix silently and note any corrections.

**Do not proceed past Step 4 until the user has approved the release notes.**

---

## Step 5 — Update CHANGELOG.md

Read `CHANGELOG.md` if it exists; if not, create it with this header:

```markdown
# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

```

Insert the approved release notes block (from Step 4) immediately after the
header, before any existing entries. Do not modify existing entries.

Verify the edit was applied by reading the first 30 lines back.

---

## Step 6 — Bump version in pyproject.toml and __init__.py

```bash
# Update version field in pyproject.toml
sed -i 's/^version = ".*"/version = "{new}"/' pyproject.toml

# Update __version__ in __init__.py (folio --version reads this at runtime)
sed -i 's/__version__ = ".*"/__version__ = "{new}"/' src/folio/__init__.py

# Verify
grep '^version' pyproject.toml
grep '__version__' src/folio/__init__.py
```

Where `{new}` is the bare version without `v` prefix (e.g. `0.1.0`).

---

## Step 7 — Commit the changelog and version bump

```bash
git add CHANGELOG.md pyproject.toml src/folio/__init__.py
git commit -m "chore(release): bump to v{new}

Generated-by: deepseek-v4-pro"
```

Confirm the commit was created with `git log -1 --oneline`.

---

## Step 8 — Tag and push

```bash
# Create annotated tag pointing at the changelog commit
git tag -a v{new} -m "v{new} — {description}"

# Push both the commit and the tag
git push origin main
git push origin v{new}
```

Confirm both pushes succeeded.

---

## Step 9 — Create GitHub Release

```bash
gh release create v{new} \
  --repo RKelln/folio \
  --title "v{new} — {description}" \
  --notes-file dist/RELEASE_NOTES_DRAFT.md
```

If `gh` is not authenticated, show the command for the user to run manually.

---

## Step 10 — Verify

```bash
gh release view v{new} --repo RKelln/folio
```

Display the final summary:

```
Release v{new} complete.

GitHub Release:  https://github.com/RKelln/folio/releases/tag/v{new}

Install:
  uv tool install git+https://github.com/RKelln/folio@v{new}
  git clone https://github.com/RKelln/folio && cd folio && uv tool install --editable .

Files modified:
  CHANGELOG.md              (v{new} entry added)
  pyproject.toml            (version bumped to {new})
  src/folio/__init__.py     (__version__ bumped to {new})
  dist/RELEASE_NOTES_DRAFT.md  (can be deleted)
```

Clean up the draft:

```bash
rm -f dist/RELEASE_NOTES_DRAFT.md
```
