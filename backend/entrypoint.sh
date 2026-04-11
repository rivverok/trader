#!/bin/bash
set -e

# Auto-run Alembic migrations when starting the API server
if echo "$@" | grep -q "uvicorn"; then
    echo "=== Running database migrations ==="
    alembic upgrade head
    echo "=== Migrations complete ==="
fi

exec "$@"
