#!/bin/bash
set -e

# Remove stale Xvfb and Chromium profile lock files if container restarted abruptly
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
rm -f /app/data/browser_profile/SingletonLock /app/data/browser_profile/SingletonCookie /app/data/browser_profile/SingletonSocket

# Ensure /app is in PYTHONPATH for Python imports
export PYTHONPATH="/app:${PYTHONPATH:-}"

echo "[Entrypoint] Starting Xvfb on display :99 (1280x800x24)..."
Xvfb :99 -screen 0 1280x800x24 -nolisten tcp &
XVFB_PID=$!

# Wait briefly for Xvfb to start
sleep 1

# Graceful cleanup on exit
cleanup() {
    echo "[Entrypoint] Shutting down Xvfb..."
    kill -TERM "$XVFB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[Entrypoint] Starting Sahibinden Discord Alert Bot..."
exec python -m src.main
