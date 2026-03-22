#!/usr/bin/env bash
# ============================================================
# Development helper — start all Celery workers in one terminal
# For production use Supervisor instead (see forex_bot.conf)
# ============================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="${PROJECT_DIR}/bot"

# Try project-local venv first, then system venv
if [ ! -f "$VENV/bin/activate" ]; then
    VENV="/opt/forex_bot_venv"
fi

if [ ! -f "$VENV/bin/activate" ]; then
    echo "❌ No virtual environment found at $VENV"
    echo "   Create one with: python3.11 -m venv $VENV"
    exit 1
fi

source "$VENV/bin/activate"
cd "$PROJECT_DIR"

echo "========================================================"
echo "  Forex Bot — Starting Celery Workers"
echo "  Project: $PROJECT_DIR"
echo "  Venv:    $VENV"
echo "========================================================"

# Check Redis is running
if ! redis-cli ping > /dev/null 2>&1; then
    echo "❌ Redis is not running. Start it: sudo systemctl start redis-server"
    exit 1
fi
echo "✅ Redis is running"

# Check Django loads cleanly
python manage.py check --deploy 2>/dev/null || python manage.py check
echo "✅ Django config OK"

# ── Start workers in background ──────────────────────────────
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

echo ""
echo "Starting workers..."
echo "(Press Ctrl+C to stop all workers)"
echo ""

# Trading worker (bot loops)
celery -A config.celery worker \
    --queues=trading \
    --concurrency=2 \
    --prefetch-multiplier=1 \
    --loglevel=info \
    --hostname=trading@%h \
    --logfile="$LOG_DIR/celery_trading.log" &
PIDS="$!"
echo "✅ Trading worker started (PID=$!)"

# Orders + Commands worker
celery -A config.celery worker \
    --queues=orders,commands \
    --concurrency=4 \
    --prefetch-multiplier=1 \
    --loglevel=info \
    --hostname=orders@%h \
    --logfile="$LOG_DIR/celery_orders.log" &
PIDS="$PIDS $!"
echo "✅ Orders/Commands worker started (PID=$!)"

# Data + Default worker
celery -A config.celery worker \
    --queues=data,default \
    --concurrency=2 \
    --prefetch-multiplier=2 \
    --loglevel=info \
    --hostname=data@%h \
    --logfile="$LOG_DIR/celery_data.log" &
PIDS="$PIDS $!"
echo "✅ Data worker started (PID=$!)"

# Backtesting worker
celery -A config.celery worker \
    --queues=backtesting \
    --concurrency=1 \
    --prefetch-multiplier=1 \
    --loglevel=info \
    --hostname=backtesting@%h \
    --logfile="$LOG_DIR/celery_backtesting.log" &
PIDS="$PIDS $!"
echo "✅ Backtesting worker started (PID=$!)"

# Celery Beat (periodic tasks)
# Remove stale pidfile if it exists
rm -f /tmp/celerybeat.pid
celery -A config.celery beat \
    --scheduler=django_celery_beat.schedulers:DatabaseScheduler \
    --loglevel=info \
    --logfile="$LOG_DIR/celery_beat.log" \
    --pidfile=/tmp/celerybeat.pid &
PIDS="$PIDS $!"
echo "✅ Celery Beat scheduler started (PID=$!)"

echo ""
echo "========================================================"
echo "  All workers running. Logs in: $LOG_DIR/"
echo ""
echo "  Monitor with:"
echo "  celery -A config.celery flower          (web UI, port 5555)"
echo "  tail -f $LOG_DIR/celery_trading.log"
echo "  tail -f $LOG_DIR/celery_beat.log"
echo "========================================================"

# Wait and cleanup on Ctrl+C
trap "echo ''; echo 'Stopping all workers...'; kill $PIDS 2>/dev/null; echo 'Done.'" INT TERM
wait