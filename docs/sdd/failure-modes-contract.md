# Failure-Modes Contract (v4 toolchain)

> Status: active · Layer: toolchain (not constitution — no ADR required) · Added: 2026-06-09
>
> Companion change: the `/sy-clarify` "decider-adjudicable" wording rule (same plan-quality
> theme). See [Clarify framing](#related-clarify-framing-rule) below.

## Problem

Two recurring asks about the plan phase:

1. **Clarify throws jargon at the wrong audience.** v4's target user is a non-developer project
   author ([threat model](../../CLAUDE.md)). Surfacing "race condition / eventual consistency" as a
   decision point is useless to them — they can't adjudicate it.
2. **Plans keep re-introducing bugs the project already hit.** Past failures in the business
   codebase (e.g. flutter-suiyin, suiyin-go) recur because nothing feeds them back into plan/review.

The naive fix — hardcode "check for these flutter-suiyin bugs" into the generic skills — is wrong:
it pollutes the v4 toolchain with one project's business specifics (violates the v4 project-scope
rule) and the static list rots.

## Contract: v4 provides the slot, the project fills it

### The slot

A single optional, project-owned file:

```
.specify/memory/failure-modes.md      # sibling of constitution.md
```

- **Owned by the project, not v4.** The business project's real failure modes live here. The v4
  generic skills stay free of any project's bug patterns.
- **Install semantics** (`bin/init.sh`, the `memory)` case): copy-if-missing, then preserved on
  every reinstall — same treatment as `constitution.md`. v4 ships a template scaffold at
  `runtime/memory/failure-modes.md`; the project edits its installed copy and v4 never overwrites it.
- **Absent / empty → skip silently.** Every consuming skill no-ops if the file is missing or holds
  only template placeholders. Projects that don't want it pay nothing; v4 itself has no such file.

### Two sections, split by stage

A failure mode is only worth checking where it can actually be caught:

| Section | Catchable in | Consumed by |
|---|---|---|
| `## Architecture-level (plan stage)` | the **plan** (missing idempotency req, no concurrency story, no offline/error state) | `/sy-plan`, `/sy-analyze` |
| `## Implementation-level (review stage)` | the **code** (null handling, off-by-one, a race in a specific handler) | C5 reviewer, `/sy-analyze` (acknowledgement only) |

Lumping code-level patterns into plan review just produces noise — a plan can't show a null deref.

### Wiring (what each skill does)

| Skill | Reads | Behavior |
|---|---|---|
| `/sy-plan` | Architecture-level only | For each entry, verify the plan has an explicit story. Unaddressed → `NEEDS CLARIFICATION: <mode> — no plan story`. **Soft gate** (surface + recommend), not a hard ERROR unless the constitution elevates it. |
| `/sy-analyze` | both sections | Detection pass **G. Known Failure-Mode Recurrence**: flag any entry not acknowledged by plan.md / tasks.md. Verifies *acknowledgement only* — analyze sees no code. Unaddressed = HIGH. |
| C5 reviewer | Implementation-level | (Downstream consumer — not yet wired.) Catches the actual code-level recurrence in the diff. |

### Feedback loop

The file is a **living** checklist, not a one-time list:

```
bug ships → recorded in failure-modes.md (+ bug-record link) → next /sy-plan & /sy-analyze catch the recurrence
                                   ▲
                         C5 reviewer appends modes it finds
```

Entries should be sourced from real bug records / postmortems (mirrored in the project's
mcp-memory-service), not hand-guessed. This keeps the list short and true.

## Non-goals / boundaries

- v4 does **not** ship any concrete failure mode — only the scaffold + the reading mechanism.
- Not a hard gate: a missing story surfaces a recommendation, it does not block. The human (or the
  autonomous role) decides whether to act.
- C5 wiring is documented here as the intended downstream consumer but is implemented separately
  (C5 is mid-flight). This contract defines the file format C5 will read.

## Related: clarify framing rule

Same plan-quality theme, shipped together. `/sy-clarify` now requires that:

1. **Options read as observable consequences, not mechanism** — "User taps Pay twice → charged
   twice" vs "Second tap ignored → one charge", not "race condition". (Jargon allowed in parens.)
2. **Decider-adjudicable only** — a question is only put to the human if its branches differ in
   something the decider can weigh (user-facing behavior, cost, time, failure consequence). Pure
   internal choices with no such difference get a sensible default + a one-line note, *not* a
   question. Fewer human decision points is a goal, consistent with the autonomous (D) role.

## Files touched

- `skills/sy-clarify/SKILL.md` — framing rule + decider-adjudicable filter
- `skills/sy-plan/SKILL.md` — load arch-level section + Failure-Mode soft gate
- `skills/sy-analyze/SKILL.md` — detection pass G + severity
- `runtime/memory/failure-modes.md` — the scaffold (installs to `.specify/memory/`)
- `docs/sdd/failure-modes-contract.md` — this doc
