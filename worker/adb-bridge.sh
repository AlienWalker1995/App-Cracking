#!/usr/bin/env bash
# Host adb-server bridge: make USB devices plugged into Windows reachable from the
# Linux worker container (which cannot see USB directly under WSL2/Docker Desktop).
#
# Run this ON THE WINDOWS HOST (Git Bash). It starts the adb server bound so the
# container can reach it; the worker then uses ADB_SERVER_SOCKET=tcp:host.docker.internal:5037.
#
# Idempotent: restarts the server bound to all interfaces on :5037.
set -uo pipefail

ADB="${ADB:-$(command -v adb || echo '/c/Users/'"$USER"'/AppData/Local/Microsoft/WinGet/Packages/Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe/scrcpy-win64-v4.1/adb')}"
PORT="${ADB_SERVER_PORT:-5037}"

echo "[*] adb: $ADB"
"$ADB" kill-server 2>/dev/null || true
# -a: listen on all interfaces so the Docker/WSL bridge (host.docker.internal) can connect.
ADB_SERVER_SOCKET="tcp:0.0.0.0:${PORT}" "$ADB" -a -P "$PORT" nodaemon server &
sleep 1
echo "[*] devices seen by the bridge:"
ADB_SERVER_SOCKET="tcp:127.0.0.1:${PORT}" "$ADB" devices -l
echo
echo "[i] Worker reaches this with:  -e ADB_SERVER_SOCKET=tcp:host.docker.internal:${PORT}"
echo "[i] Leave this running while you drive Tier-1 (Ctrl-C to stop)."
