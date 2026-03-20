#!/usr/bin/env bash
# ============================================================
# ABSOLUTE PATH: /opt/forex_bot/dev_quickstart.sh
# One-command dev environment startup
# Usage: bash dev_quickstart.sh
# Starts: Daphne + Celery workers in background
# ============================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="${PROJECT_DIR}/bot"
[ ! -f "$VENV/bin/activate" ] && VENV="/opt/forex_bot_venv"

source "$VENV/bin/activate"
cd "$PROJECT_DIR"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${CYAN}[INFO]${NC} $1"; }
ok()   { echo -e "${GREEN}[ OK ]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

echo ""
echo "════════════════════════════════════════"
echo "  ForexBot — Dev Quick Start"
echo "════════════════════════════════════════"

# Check Redis
if ! redis-cli ping > /dev/null 2>&1; then
    warn "Redis not running — starting..."
    sudo systemctl start redis-server
fi
ok "Redis running"

# Check PostgreSQL
if ! pg_isready -q 2>/dev/null; then
    warn "PostgreSQL not running — starting..."
    sudo systemctl start postgresql
fi
ok "PostgreSQL running"

# Find a free port
PORT=8001
for p in 8001 8002 8003 8004 8005; do
    if ! ss -tlnp 2>/dev/null | grep -q ":$p "; then
        PORT=$p; break
    fi
done
info "Using port $PORT"

LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

# Kill previous background workers from this script
[ -f "/tmp/forex_bot_pids" ] && {
    info "Stopping previous workers..."
    while IFS= read -r pid; do kill "$pid" 2>/dev/null || true; done < /tmp/forex_bot_pids
    rm /tmp/forex_bot_pids
}

# Start Celery workers in background
PIDS=""
celery -A config.celery worker \
    --queues=trading,orders,commands,data,default,backtesting \
    --concurrency=2 --prefetch-multiplier=1 \
    --loglevel=info \
    --logfile="$LOG_DIR/celery_dev.log" &
PIDS="$! "
ok "Celery worker started (PID=$!)"

# Start Celery Beat
rm -f /tmp/celerybeat.pid
celery -A config.celery beat \
    --scheduler=django_celery_beat.schedulers:DatabaseScheduler \
    --loglevel=info \
    --logfile="$LOG_DIR/celery_beat.log" \
    --pidfile=/tmp/celerybeat.pid &
PIDS="$PIDS$!"
ok "Celery Beat started (PID=$!)"

echo "$PIDS" > /tmp/forex_bot_pids

echo ""
echo "════════════════════════════════════════"
ok "All background services started"
echo ""
echo "  Logs:      tail -f $LOG_DIR/celery_dev.log"
echo "  Stop all:  bash dev_quickstart.sh (re-run to restart)"
echo ""
echo "  Starting Daphne on port $PORT..."
echo "  Dashboard: http://localhost:$PORT/"
echo "  API docs:  http://localhost:$PORT/api/docs/"
echo "════════════════════════════════════════"
echo ""

# Trap Ctrl+C to clean up background workers
trap "echo ''; info 'Stopping workers...'; kill $PIDS 2>/dev/null; rm -f /tmp/forex_bot_pids; echo 'Done.'" INT TERM

# Start Daphne in foreground (so Ctrl+C stops everything)
daphne -b 127.0.0.1 -p "$PORT" config.asgi:application