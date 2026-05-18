# sy.git.push

Push current branch to the remote (`origin`).

## Pre-checks

Before pushing:

- Verify working tree is clean (no uncommitted changes)
- Verify currently on a branch (not detached HEAD)
- Read current branch name: `git branch --show-current`

If pre-checks fail, output structured error and abort (do NOT push).

## Action

Detect upstream tracking status, then push:

```bash
BRANCH=$(git branch --show-current)
if git rev-parse --abbrev-ref --symbolic-full-name "@{u}" >/dev/null 2>&1; then
  # Upstream is tracked
  git push origin HEAD
else
  # First push for this branch
  git push -u origin "$BRANCH"
fi
```

## Failure handling

| Failure type | Action |
|---|---|
| Network timeout / unreachable | Report structured error with `code: PUSH_NETWORK_ERROR`, do NOT retry automatically |
| Remote rejected (non-fast-forward) | Report `code: PUSH_REJECTED`, request human (NEVER auto force-push) |
| No-op (nothing to push) | Report success with `is_noop: true` |

## Output schema

```yaml
type: object
required: [pushed, branch]
properties:
  pushed:
    type: boolean
    description: true if push succeeded; false if no-op or error
  branch:
    type: string
  remote:
    type: string
    default: origin
  is_first_push:
    type: boolean
    description: true if upstream was set via -u
  is_noop:
    type: boolean
    description: true if nothing to push
  message:
    type: string
```

## Notes

- This command **NEVER** force-pushes (no `-f` / `--force-with-lease`).
- This command **only** pushes the current branch to `origin`. To push elsewhere, request human action.
- Used by the `after_constitution` hook (mandatory for all role profiles).
- Other `after_*` hooks may or may not use this command depending on role profile.
