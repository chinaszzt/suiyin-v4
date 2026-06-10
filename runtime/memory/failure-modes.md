# Known Failure Modes

> **What this is.** A per-project, living checklist of failure modes this codebase has
> *actually hit* — sourced from real bug records / postmortems, not hand-guessed. The
> toolchain reads it automatically:
>
> | Stage | Reads which section | Skill | What it does |
> |---|---|---|---|
> | Planning | `## Architecture-level (plan stage)` | `/sy-plan` | For each entry, checks the plan has an explicit story; flags `NEEDS CLARIFICATION` if not. |
> | Artifact review | both sections | `/sy-analyze` | Flags any entry not acknowledged by plan.md / tasks.md. |
> | Code review | `## Implementation-level (review stage)` | C5 reviewer | Catches the actual code-level recurrence in the diff. |
>
> **Scope rule.** This file is project-owned. It lives in *this* project's `.specify/memory/`,
> NOT in the v4 toolchain — keep the v4 generic skills free of any one project's bug patterns.
>
> **Two sections, by stage.** Architecture-level failures are visible in a *plan* (a missing
> idempotency requirement, no concurrency story, no offline/error state). Implementation-level
> failures are only visible in *code* (null handling, off-by-one, a race in a specific handler) —
> putting those in the plan-stage section just produces noise. Put each entry where it can be caught.
>
> **Feedback loop.** When a bug ships, record it here (plus its bug-record link) so the next
> plan/review catches the recurrence. The C5 reviewer should append modes it finds, too.
>
> **Empty is fine.** Delete the example rows below and leave a section empty until you have a
> real, recurring failure to record. The skills skip empty / placeholder-only sections silently.

---

## Architecture-level (plan stage)

<!-- Failure modes a /sy-plan reviewer can catch by reading the PLAN. One row per recurring mode.
     Delete these examples; replace with real entries from your bug records. -->

| Failure mode | User-visible symptom | Plan must show | First seen (bug ref) |
|---|---|---|---|
| _e.g._ Double-submit not idempotent | User taps a button twice → action runs twice (double charge / duplicate record) | An idempotency key or dedup story for every state-changing action | _e.g._ #986 |
| _e.g._ No concurrency story for shared edits | Two users edit the same record → one silently overwrites the other | A conflict-resolution rule (last-write-wins / merge / lock) stated in the plan | — |
| _e.g._ Missing offline / error state | Network drops mid-flow → blank screen or stuck spinner, no retry | An explicit error/empty/loading/offline state per critical flow | — |

## Implementation-level (review stage)

<!-- Failure modes only visible in CODE — for the C5 reviewer / test design, not plan review. -->

| Failure mode | How it bites | Reviewer/test should check | First seen (bug ref) |
|---|---|---|---|
| _e.g._ Unhandled null from optional field | Crash / blank when an optional API field is absent | Null/absent handling on every optional field read | — |
| _e.g._ Index declared in wrong DB/scope | Query slow in prod despite "working" locally | Verify index lands in the prod DB, from raw `getIndexes()` — not a local explain | _e.g._ #986 |
