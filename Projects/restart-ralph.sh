#!/bin/bash
# restart-ralph.sh — Clean restart of OpenClaw with Telegram stale poll fix
#
# PROBLEM: When OpenClaw restarts, the previous Telegram getUpdates long-poll
# may still be active (up to 30s timeout). A new instance polling the same bot
# token causes a 409 Conflict, and Telegram blocks both from receiving messages.
#
# FIX: Stop the container, wait for the stale poll to expire (35s), clear any
# pending updates, then start fresh.
#
# Usage: sudo /home/openclaw/restart-ralph.sh

set -e

OPENCLAW_USER="openclaw"
OPENCLAW_UID=$(id -u $OPENCLAW_USER)
export XDG_RUNTIME_DIR="/run/user/$OPENCLAW_UID"
BOT_TOKEN="8081129150:AAFz0UZsKPx2qgsKhMPbQxl_Rld2YxuhZ1U"

run_podman() {
    cd /tmp
    sudo -u "$OPENCLAW_USER" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" podman "$@"
}

echo "[1/5] Stopping OpenClaw..."
run_podman stop openclaw || true

echo "[2/5] Waiting 35s for Telegram stale long-poll to expire..."
sleep 35

echo "[3/5] Clearing pending Telegram updates..."
curl -sf "https://api.telegram.org/bot${BOT_TOKEN}/getUpdates?offset=-1&timeout=1" > /dev/null 2>&1 || true

echo "[4/5] Starting OpenClaw..."
run_podman start openclaw
sleep 3

echo "[5/5] Installing custom skills..."
run_podman exec openclaw /home/node/.openclaw/custom-skills/install-skills.sh

echo ""
echo "=== Status ==="
run_podman logs --tail 5 openclaw 2>&1 | grep -v "^$"
echo ""
run_podman ps --format "{{.Names}} {{.Status}}" | grep openclaw
