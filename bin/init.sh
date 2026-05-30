#!/usr/bin/env bash
# suiyin-flow init — initialize SDD toolchain in a target project
#
# Self-contained: does NOT depend on spec-kit CLI or any external tool besides git + bash.
#
# Usage:
#   bash /path/to/suiyin-v4/bin/init.sh                    # init current dir
#   bash /path/to/suiyin-v4/bin/init.sh /path/to/project   # init specific dir

set -euo pipefail

# ─── Detect v4 toolchain dir ───
V4_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ─── Detect target ───
TARGET_DIR="${1:-$PWD}"
if [ ! -d "$TARGET_DIR" ]; then
  echo "Error: target dir does not exist: $TARGET_DIR" >&2
  exit 1
fi
TARGET_DIR="$(cd "$TARGET_DIR" && pwd)"
PROJECT_NAME="$(basename "$TARGET_DIR")"

echo "=> Initializing suiyin-flow"
echo "   v4 toolchain : $V4_DIR"
echo "   Target project: $TARGET_DIR ($PROJECT_NAME)"
echo ""

# ─── 1. Validate git repo ───
# Use git rev-parse so worktrees (where .git is a file, not a directory) also pass.
if ! git -C "$TARGET_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: $TARGET_DIR is not a git repository" >&2
  echo "Hint:  run 'git init' first or clone an existing repo" >&2
  exit 1
fi

# ─── 2. Validate v4 toolchain has skills + runtime ───
if [ ! -d "$V4_DIR/skills" ] || [ ! -d "$V4_DIR/runtime" ]; then
  echo "Error: v4 toolchain at $V4_DIR is missing skills/ or runtime/" >&2
  echo "Hint:  did you clone suiyin-v4 fully?" >&2
  exit 1
fi

# ─── 3. Detect re-install vs first-install ───
IS_REINSTALL=false
if [ -d "$TARGET_DIR/.claude/skills" ] && ls "$TARGET_DIR/.claude/skills/sy-"* >/dev/null 2>&1; then
  IS_REINSTALL=true
  echo "==> Detected previous v4 install — re-installing (user content preserved)"
else
  echo "==> First-time install"
fi

# ─── 4. Clean previous v4 toolchain files (preserve user content) ───
if [ "$IS_REINSTALL" = true ]; then
  # 4a. Remove all sy-* skills (will be reinstalled fresh)
  find "$TARGET_DIR/.claude/skills" -maxdepth 1 -name "sy-*" -type d -exec rm -rf {} + 2>/dev/null || true

  # 4b. Remove v4 runtime subdirs (templates / scripts / extensions / workflows / integrations)
  #     Preserve memory/ (user constitution, ADR) and specs/ (user feature specs)
  for subdir in templates scripts extensions workflows integrations; do
    rm -rf "$TARGET_DIR/.specify/$subdir"
  done
  rm -f "$TARGET_DIR/.specify/extensions.yml" \
        "$TARGET_DIR/.specify/init-options.json" \
        "$TARGET_DIR/.specify/integration.json"

  # 4c. Report what was preserved
  if [ -d "$TARGET_DIR/.specify/memory" ] && [ -n "$(ls -A $TARGET_DIR/.specify/memory 2>/dev/null)" ]; then
    echo "   ✓ preserved .specify/memory/ (user content: constitution / ADRs / ...)"
  fi
  if [ -d "$TARGET_DIR/.specify/specs" ]; then
    spec_count=$(ls -1 "$TARGET_DIR/.specify/specs" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$spec_count" -gt 0 ]; then
      echo "   ✓ preserved .specify/specs/ ($spec_count user specs)"
    fi
  fi
fi

# ─── 5. Create target directories ───
mkdir -p "$TARGET_DIR/.claude/skills"
mkdir -p "$TARGET_DIR/.specify"

# ─── 6. Install skills (the /sy-* slash commands) ───
echo "==> Installing skills (slash commands)"
cp -r "$V4_DIR/skills/"* "$TARGET_DIR/.claude/skills/"
skill_count=$(ls -1 "$V4_DIR/skills/" | wc -l | tr -d ' ')
echo "   $skill_count skills installed (/sy-*)"

# ─── 7. Install runtime (templates + scripts + extensions) ───
echo "==> Installing runtime (templates + scripts + extensions)"
# User-tunable items (memory/, role-profile.yml): preserve, only install v4 default if missing
# Other items (templates/scripts/extensions/etc): replace with v4 latest each reinstall
for item in "$V4_DIR/runtime/"*; do
  [ -e "$item" ] || continue
  name=$(basename "$item")
  case "$name" in
    memory)
      # Memory: preserve user files, only copy v4 defaults for missing files
      mkdir -p "$TARGET_DIR/.specify/memory"
      for f in "$item"/*; do
        [ -e "$f" ] || continue
        target_f="$TARGET_DIR/.specify/memory/$(basename "$f")"
        if [ ! -e "$target_f" ]; then
          cp -r "$f" "$target_f"
          echo "   - memory/$(basename "$f") (v4 default, no user file existed)"
        fi
      done
      ;;
    role-profile.yml)
      # User-tunable config: preserve if exists, install v4 default if missing
      target_f="$TARGET_DIR/.specify/$name"
      if [ ! -e "$target_f" ]; then
        cp "$item" "$target_f"
        echo "   - $name (v4 default: autonomous)"
      else
        echo "   - $name preserved (user-tuned, not overwritten)"
      fi
      ;;
    claude-settings.json)
      # Handled in step 8 (installed to .claude/settings.json), skip here
      ;;
    *)
      # Other (templates/scripts/extensions/workflows/integrations): replace with v4 latest
      cp -r "$item" "$TARGET_DIR/.specify/"
      ;;
  esac
done
echo "   .specify/ populated"

# ─── 6. Override constitution template with v4 customization ───
if [ -f "$V4_DIR/templates/constitution-template.md" ]; then
  cp "$V4_DIR/templates/constitution-template.md" "$TARGET_DIR/.specify/templates/"
  echo "==> Installed v4-customized constitution-template.md"
fi

# ─── 7. Write project README ───
echo "==> Writing project README"
if [ ! -f "$TARGET_DIR/README.md" ] || [ ! -s "$TARGET_DIR/README.md" ]; then
  sed "s|{{PROJECT_NAME}}|$PROJECT_NAME|g" "$V4_DIR/templates/README-v5.md" > "$TARGET_DIR/README.md"
  echo "   - README.md (project: $PROJECT_NAME)"
else
  sed "s|{{PROJECT_NAME}}|$PROJECT_NAME|g" "$V4_DIR/templates/README-v5.md" > "$TARGET_DIR/README.suiyin-suggested.md"
  echo "   - README.md exists, suggested version saved to README.suiyin-suggested.md"
fi

# ─── 8. Install .claude/settings.json (git allowlist for auto-commit/push) ───
if [ -f "$V4_DIR/runtime/claude-settings.json" ]; then
  mkdir -p "$TARGET_DIR/.claude"
  if [ ! -f "$TARGET_DIR/.claude/settings.json" ]; then
    cp "$V4_DIR/runtime/claude-settings.json" "$TARGET_DIR/.claude/settings.json"
    echo "==> Installed .claude/settings.json (git allowlist for auto-commit/push)"
  else
    cp "$V4_DIR/runtime/claude-settings.json" "$TARGET_DIR/.claude/settings.suiyin-suggested.json"
    echo "   - .claude/settings.json exists, suggested version saved to .claude/settings.suiyin-suggested.json"
  fi
fi

# ─── 9. Write CLAUDE.md (Claude Code project hint) ───
if [ ! -f "$TARGET_DIR/CLAUDE.md" ]; then
  cat > "$TARGET_DIR/CLAUDE.md" <<EOF
<!-- SUIYIN-FLOW START -->
This project uses [suiyin-flow](https://github.com/chinaszzt/suiyin-v4) for SDD workflow.

Slash commands: \`/sy-constitution\` \`/sy-specify\` \`/sy-clarify\` \`/sy-plan\` \`/sy-tasks\` \`/sy-implement\` \`/sy-analyze\`

Role profile: see \`.specify/role-profile.yml\` (default: autonomous).
Git automation: \`/sy-constitution\` always auto-commits + auto-pushes (bootstrap special case);
other \`/sy-*\` follow role-profile.

See \`README.md\` for the full workflow.
<!-- SUIYIN-FLOW END -->
EOF
  echo "   - CLAUDE.md created"
fi

# ─── 9. Print next-step instructions ───
cat <<EOF

✓ suiyin-flow initialized.

──────────────────────────────────────────────
Next step: 协商 constitution
──────────────────────────────────────────────

1. Open this directory in Claude Code:
     cd $TARGET_DIR
     claude

2. Run the slash command:
     /sy-constitution

AI will guide you through 5-10 questions to generate
your project's constitution.md (at .specify/memory/constitution.md).

See README.md for the full workflow and all available commands.

EOF
