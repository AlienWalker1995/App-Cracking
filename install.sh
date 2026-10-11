#!/usr/bin/env bash
# Unified multi-harness installer for the app-cracker skill.
#
# Copies the canonical skill (skills/app-cracker/SKILL.md) and the per-harness
# wrapper files into the location each agent harness expects. One source of
# truth: the canonical SKILL.md; the wrappers point at it.
#
# Usage: ./install.sh <claude|codex|cursor|gemini|hermes|all> [--dry-run]
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY_RUN=0

usage() {
  cat <<USAGE
Usage: ./install.sh <claude|codex|cursor|gemini|hermes|all> [--dry-run]

Install the app-cracker skill into a supported agent harness.

Targets:
  claude   copy skills/app-cracker/ into \$CLAUDE_SKILLS_DIR (default ~/.claude/skills)
  codex    copy AGENTS.md into \$CODEX_HOME (default ~/.codex)
  cursor   copy .cursor/rules/app-cracker.mdc into \$CURSOR_RULES_DIR (default ./.cursor/rules)
  gemini   copy GEMINI.md + gemini-extension.json into \$GEMINI_EXT_DIR (default ~/.gemini/extensions/app-cracker)
  hermes   copy skills/app-cracker/SKILL.md into \$HERMES_SKILLS_DIR (default ~/.hermes/skills/app-cracker)
  all      every target above

Options:
  --dry-run   print the mkdir/copy actions without performing them
  --help      show this help
USAGE
}

# --- argument parsing ---
TARGET=""
for arg in "$@"; do
  case "$arg" in
    --help|-h)
      usage
      exit 0
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    claude|codex|cursor|gemini|hermes|all)
      TARGET="$arg"
      ;;
    *)
      echo "install.sh: unknown argument: $arg" >&2
      usage
      exit 2
      ;;
  esac
done

if [ -z "$TARGET" ]; then
  usage
  exit 2
fi

# --- per-target installers ---
install_claude() {
  local dest="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}/app-cracker"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] mkdir -p $dest"
    echo "[dry-run] cp -r $SRC/skills/app-cracker/. $dest/"
  else
    mkdir -p "$dest"
    cp -r "$SRC/skills/app-cracker/." "$dest/"
    echo "installed claude -> $dest"
  fi
}

install_codex() {
  local dest="${CODEX_HOME:-$HOME/.codex}/AGENTS.md"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] mkdir -p $(dirname "$dest")"
    echo "[dry-run] cp -f $SRC/AGENTS.md $dest"
  else
    mkdir -p "$(dirname "$dest")"
    cp -f "$SRC/AGENTS.md" "$dest"
    echo "installed codex -> $dest"
  fi
  echo "note: Codex also reads a repo-root AGENTS.md automatically when run inside this repo."
}

install_cursor() {
  local src="$SRC/.cursor/rules/app-cracker.mdc"
  local dest="${CURSOR_RULES_DIR:-$PWD/.cursor/rules}/app-cracker.mdc"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] mkdir -p $(dirname "$dest")"
    echo "[dry-run] cp -f $src $dest"
  else
    mkdir -p "$(dirname "$dest")"
    if [ "$(realpath "$src")" = "$(realpath "$dest")" ]; then
      echo "installed cursor -> $dest (already in place)"
    else
      cp -f "$src" "$dest"
      echo "installed cursor -> $dest"
    fi
  fi
}

install_gemini() {
  local dest="${GEMINI_EXT_DIR:-$HOME/.gemini/extensions/app-cracker}"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] mkdir -p $dest"
    echo "[dry-run] cp -f $SRC/GEMINI.md $dest/GEMINI.md"
    echo "[dry-run] cp -f $SRC/gemini-extension.json $dest/gemini-extension.json"
  else
    mkdir -p "$dest"
    cp -f "$SRC/GEMINI.md" "$dest/GEMINI.md"
    cp -f "$SRC/gemini-extension.json" "$dest/gemini-extension.json"
    echo "installed gemini -> $dest"
  fi
}

install_hermes() {
  local dest="${HERMES_SKILLS_DIR:-$HOME/.hermes/skills/app-cracker}/SKILL.md"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] mkdir -p $(dirname "$dest")"
    echo "[dry-run] cp -f $SRC/skills/app-cracker/SKILL.md $dest"
  else
    mkdir -p "$(dirname "$dest")"
    cp -f "$SRC/skills/app-cracker/SKILL.md" "$dest"
    echo "installed hermes -> $dest"
  fi
}

case "$TARGET" in
  claude) install_claude ;;
  codex)  install_codex ;;
  cursor) install_cursor ;;
  gemini) install_gemini ;;
  hermes) install_hermes ;;
  all)
    install_claude
    install_codex
    install_cursor
    install_gemini
    install_hermes
    ;;
esac
