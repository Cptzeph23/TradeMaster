#!/usr/bin/env bash
# ============================================================
# ABSOLUTE PATH: /opt/forex_bot/test_celery_8001.sh
# Phase I — Celery Worker tests
# ============================================================
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="${PROJECT_DIR}/bot"
[ ! -f "$VENV/bin/activate" ] && VENV="/opt/forex_bot_venv"

source "$VENV/bin/activate" 2>/dev/null || true
cd "$PROJECT_DIR"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m';  NC='\033[0m'

pass() { echo -e "${GREEN}  ✅ PASS${NC} — $1"; }
fail() { echo -e "${RED}  ❌ FAIL${NC} — $1"; }
warn() { echo -e "${YELLOW}  ⚠  WARN${NC} — $1"; }
section() {
  echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${YELLOW}  $1${NC}"
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

section "TEST 1 — Redis connectivity"
if redis-cli ping > /dev/null 2>&1; then
  pass "Redis is running"
  INFO=$(redis-cli info server | grep redis_version)
  echo "  $INFO"
else
  fail "Redis is NOT running"
  echo "  Start with: sudo systemctl start redis-server"
  exit 1
fi

section "TEST 2 — Django + Celery app loads"
python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from config.celery import app
print(f'  Celery app: {app.main}')
print(f'  Broker:     {app.conf.broker_url}')
print(f'  Backend:    {app.conf.result_backend}')
" && pass "Celery app loads cleanly" || fail "Celery app failed to load"

section "TEST 3 — Registered tasks"
python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from config.celery import app
tasks = sorted([t for t in app.tasks.keys() if not t.startswith('celery.')])
print(f'  Registered tasks ({len(tasks)}):')
for t in tasks:
    print(f'    • {t}')
" && pass "Task registry loaded" || fail "Task registry failed"

section "TEST 4 — Beat schedule"
python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from config.celery import app
sched = app.conf.beat_schedule
print(f'  Scheduled tasks ({len(sched)}):')
for name, cfg in sched.items():
    print(f'    • {name}: {cfg[\"task\"]}')
" && pass "Beat schedule configured" || fail "Beat schedule failed"

section "TEST 5 — Queue configuration"
python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from config.celery import app
queues = [q.name for q in app.conf.task_queues]
print(f'  Queues: {queues}')
assert 'trading' in queues
assert 'orders' in queues
assert 'backtesting' in queues
assert 'data' in queues
assert 'commands' in queues
" && pass "All 5 queues configured" || fail "Queue configuration failed"

section "TEST 6 — Worker ping (requires running worker)"
echo "  Sending ping to any available Celery workers..."
PING=$(python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from config.celery import app
result = app.control.ping(timeout=3)
if result:
    for worker, response in result[0].items():
        print(f'  Worker: {worker} → {response}')
    print('WORKERS_FOUND')
else:
    print('NO_WORKERS')
" 2>/dev/null)

if echo "$PING" | grep -q "WORKERS_FOUND"; then
    pass "Active workers responded to ping"
    echo "$PING" | grep -v "WORKERS_FOUND"
else
    warn "No workers running yet"
    echo "  Start workers with: bash start_workers.sh"
    echo "  (Workers not required for server-side tests)"
fi

section "TEST 7 — Debug task (fire-and-forget)"
python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from config.celery import app

# Fire debug task — will queue even without a worker
result = app.signature('config.celery.debug_task').delay()
print(f'  Task queued: {result.id}')
print('  QUEUED')
" 2>/dev/null && pass "Debug task queued successfully" || warn "Could not queue task (Redis may need restart)"

section "TEST 8 — Django-Celery-Beat DB tables"
python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule
pt_count = PeriodicTask.objects.count()
print(f'  PeriodicTask rows: {pt_count}')
print('OK')
" 2>/dev/null
if [ $? -eq 0 ]; then
  pass "django-celery-beat tables exist"
else
  fail "django-celery-beat tables missing — run: python manage.py migrate"
fi

section "TEST 9 — Celery Result backend"
python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django_celery_results.models import TaskResult
count = TaskResult.objects.count()
print(f'  TaskResult rows: {count}')
print('OK')
" 2>/dev/null && pass "django-celery-results tables exist" \
  || fail "Tables missing — run: python manage.py migrate"

echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  PHASE I TESTS COMPLETE${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  To start all workers for full end-to-end testing:"
echo ""
echo "  Terminal 1:  python manage.py runserver 8001"
echo "  Terminal 2:  bash start_workers.sh"
echo "  Terminal 3:  bash test_celery_8001.sh"
echo ""
echo "  Monitor workers: celery -A config.celery flower"
echo "    (install flower: pip install flower)"