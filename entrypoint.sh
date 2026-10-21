#!/bin/bash
set -e

# Remove stale Xvfb lock files if container restarted abruptly
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99

echo "[Entrypoint] Starting Xvfb on display :99 (1280x800x24)..."
Xvfb :99 -screen 0 1280x800x24 -nolisten tcp -nolisten unix &
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
exec python src/main.py
