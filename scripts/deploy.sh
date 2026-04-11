#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# deploy.sh — Rebuild and restart the AI Trader platform
#
# Usage:
#   bash scripts/deploy.sh              # rebuild all services
#   bash scripts/deploy.sh frontend     # rebuild only frontend
#   bash scripts/deploy.sh backend      # rebuild api + worker + scheduler
#   bash scripts/deploy.sh --no-build   # restart without rebuilding
# ──────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

BACKEND_SERVICES="api worker scheduler"
FRONTEND_SERVICES="frontend caddy"
ALL_SERVICES="postgres redis $BACKEND_SERVICES $FRONTEND_SERVICES"

TARGET="${1:-all}"

echo "========================================"
echo "  AI Trader — Deploy"
echo "========================================"
echo ""

# ── Git pull (skip if --no-build) ─────────────────────────
if [ "$TARGET" != "--no-build" ] && command -v git &>/dev/null && [ -d .git ]; then
    echo "==> Pulling latest code..."
    git pull || echo "    (git pull skipped — not on a branch or no remote)"
    echo ""
fi

# ── Build ─────────────────────────────────────────────────
if [ "$TARGET" = "--no-build" ]; then
    echo "==> Skipping build (--no-build)"
    echo ""
elif [ "$TARGET" = "frontend" ]; then
    echo "==> Building frontend..."
    docker compose build frontend
    echo ""
elif [ "$TARGET" = "backend" ]; then
    echo "==> Building backend services..."
    docker compose build api
    echo ""
elif [ "$TARGET" = "all" ]; then
    echo "==> Building all services..."
    docker compose build api frontend
    echo ""
else
    echo "Unknown target: $TARGET"
    echo "Usage: deploy.sh [all|frontend|backend|--no-build]"
    exit 1
fi

# ── Database migrations ───────────────────────────────────
echo "==> Starting database..."
docker compose up -d postgres redis
echo "    Waiting for database to be healthy..."
sleep 3

echo "==> Running database migrations..."
docker compose run --rm api alembic upgrade head
echo ""

# ── Restart services ──────────────────────────────────────
if [ "$TARGET" = "frontend" ]; then
    echo "==> Restarting frontend..."
    docker compose up -d $FRONTEND_SERVICES
elif [ "$TARGET" = "backend" ]; then
    echo "==> Restarting backend..."
    docker compose up -d $BACKEND_SERVICES
else
    echo "==> Restarting all services..."
    docker compose up -d
fi
echo ""

# ── Status ────────────────────────────────────────────────
echo "==> Services:"
docker compose ps
echo ""
echo "========================================"
echo "  Deploy complete!"
echo "  Open http://localhost to view the app"
echo "========================================"
