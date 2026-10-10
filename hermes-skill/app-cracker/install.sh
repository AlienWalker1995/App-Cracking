#!/usr/bin/env bash
# Idempotently seed the app-cracker skill into the Hermes brain volume.
#
# Hermes loads skills from its hermes-home named volume at
# /home/hermes/.hermes/skills/ (also visible as /workspace/data/hermes/skills/).
# The source of truth is THIS repo; this script copies it in. Safe to re-run.
#
# Usage: ./install.sh            (defaults: container <agent-container>)
#        CONTAINER=<agent-container> ./install.sh
set -euo pipefail

CONTAINER="${CONTAINER:-<agent-container>}"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="/home/hermes/.hermes/skills/app-cracker"

echo "[*] Seeding app-cracker skill into $CONTAINER:$DEST"
docker exec "$CONTAINER" mkdir -p "$DEST"
# The repo is mirror-mounted at /c/dev inside Hermes, so copy from there in-container
# (keeps a single source of truth rather than docker cp'ing a host path).
docker exec "$CONTAINER" sh -c "cp -f <REPO>/hermes-skill/app-cracker/SKILL.md '$DEST/SKILL.md'"
docker exec "$CONTAINER" sh -c "ls -la '$DEST'"
echo "[+] Done. Restart is not required; Hermes rescans skills on next turn."
