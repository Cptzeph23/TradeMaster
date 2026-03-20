#!/usr/bin/env bash
# ============================================================
# ABSOLUTE PATH: /opt/forex_bot/deploy.sh
# Full production deployment script
# Run after placing all project files on the server:
#   bash deploy.sh
# ============================================================
set -euo pipefail

PROJECT_DIR="/opt/forex_bot"
VENV_DIR="/opt/forex_bot_venv"
SERVICE_USER="forex"

# ── Colours ──────────────────────────────────────────────────
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${CYAN}  [INFO]${NC} $1"; }
success() { echo -e "${GREEN}  [OK]${NC}   $1"; }
warn()    { echo -e "${YELLOW}  [WARN]${NC} $1"; }

echo ""
echo "════════════════════════════════════════════"
echo "  ForexBot — Production Deployment"
echo "════════════════════════════════════════════"
echo ""

# ── 1. Activate virtualenv ────────────────────────────────────
info "Activating virtualenv..."
source "$VENV_DIR/bin/activate"
success "Virtualenv active"

# ── 2. Install/update dependencies ───────────────────────────
info "Installing Python dependencies..."
pip install -r "$PROJECT_DIR/requirements.txt" --quiet
success "Dependencies installed"

# ── 3. Run database migrations ────────────────────────────────
info "Running database migrations..."
cd "$PROJECT_DIR"
python manage.py migrate --noinput
success "Migrations complete"

# ── 4. Collect static files ───────────────────────────────────
info "Collecting static files..."
python manage.py collectstatic --noinput --clear
success "Static files collected"

# ── 5. Django system check ────────────────────────────────────
info "Running Django system check..."
python manage.py check --deploy 2>/dev/null || \
python manage.py check
success "System check passed"

# ── 6. Generate Fernet encryption key if missing ─────────────
if ! grep -q "^ENCRYPTION_KEY=" "$PROJECT_DIR/.env" || \
   grep -q "^ENCRYPTION_KEY=$" "$PROJECT_DIR/.env"; then
    info "Generating Fernet encryption key..."
    FERNET_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    if grep -q "^ENCRYPTION_KEY=" "$PROJECT_DIR/.env"; then
        sed -i "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=$FERNET_KEY|" "$PROJECT_DIR/.env"
    else
        echo "ENCRYPTION_KEY=$FERNET_KEY" >> "$PROJECT_DIR/.env"
    fi
    success "Encryption key generated"
    warn "SAVE THIS KEY — losing it means broker API keys cannot be decrypted!"
fi

# ── 7. Create Celery periodic tasks in DB ────────────────────
info "Setting up Celery Beat schedule in database..."
python manage.py shell << 'PYEOF'
from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule
from django.utils import timezone
import json

# Every 60 seconds — fetch active symbols
interval_60s, _ = IntervalSchedule.objects.get_or_create(
    every=60, period=IntervalSchedule.SECONDS
)
PeriodicTask.objects.update_or_create(
    name='Fetch active symbols every 60s',
    defaults={
        'task':     'apps.market_data.tasks.fetch_all_active_symbols',
        'interval': interval_60s,
        'enabled':  True,
    }
)

# Every 5 minutes — bot health check
interval_5m, _ = IntervalSchedule.objects.get_or_create(
    every=5, period=IntervalSchedule.MINUTES
)
PeriodicTask.objects.update_or_create(
    name='Bot health check every 5min',
    defaults={
        'task':     'workers.scheduler.health_check_bots',
        'interval': interval_5m,
        'enabled':  True,
    }
)

# Every 15 minutes — sync account balances
interval_15m, _ = IntervalSchedule.objects.get_or_create(
    every=15, period=IntervalSchedule.MINUTES
)
PeriodicTask.objects.update_or_create(
    name='Sync account balances every 15min',
    defaults={
        'task':     'workers.scheduler.sync_all_account_balances',
        'interval': interval_15m,
        'enabled':  True,
    }
)

# Daily report at midnight UTC
midnight, _ = CrontabSchedule.objects.get_or_create(
    minute=0, hour=0,
    day_of_week='*', day_of_month='*', month_of_year='*',
    timezone='UTC'
)
PeriodicTask.objects.update_or_create(
    name='Daily performance report',
    defaults={
        'task':    'workers.scheduler.generate_daily_report',
        'crontab': midnight,
        'enabled': True,
    }
)

# Hourly tick purge
hourly, _ = CrontabSchedule.objects.get_or_create(
    minute=0, hour='*',
    day_of_week='*', day_of_month='*', month_of_year='*',
    timezone='UTC'
)
PeriodicTask.objects.update_or_create(
    name='Purge old ticks hourly',
    defaults={
        'task':    'apps.market_data.tasks.purge_old_ticks',
        'crontab': hourly,
        'enabled': True,
    }
)

print("Celery Beat tasks configured in database.")
PYEOF
success "Celery Beat schedule configured"

# ── 8. Reload Supervisor ──────────────────────────────────────
info "Reloading Supervisor processes..."
sudo supervisorctl reread  2>/dev/null || warn "supervisorctl reread failed — run manually"
sudo supervisorctl update  2>/dev/null || warn "supervisorctl update failed — run manually"
sudo supervisorctl restart all 2>/dev/null || warn "supervisorctl restart failed — run manually"
success "Supervisor reloaded"

# ── 9. Reload Nginx ───────────────────────────────────────────
info "Testing and reloading Nginx..."
sudo nginx -t 2>/dev/null && sudo systemctl reload nginx 2>/dev/null \
    || warn "Nginx reload failed — run: sudo nginx -t"
success "Nginx reloaded"

# ── 10. Verify services ───────────────────────────────────────
echo ""
info "Service status:"
echo ""
sudo supervisorctl status 2>/dev/null || true
echo ""
redis-cli ping > /dev/null 2>&1 && echo -e "  Redis:     ${GREEN}RUNNING${NC}" \
    || echo -e "  Redis:     ${YELLOW}NOT RUNNING${NC} — sudo systemctl start redis-server"
sudo systemctl is-active postgresql > /dev/null 2>&1 \
    && echo -e "  PostgreSQL:${GREEN}RUNNING${NC}" \
    || echo -e "  PostgreSQL:${YELLOW}NOT RUNNING${NC} — sudo systemctl start postgresql"

echo ""
echo "════════════════════════════════════════════"
echo -e "${GREEN}  Deployment complete!${NC}"
echo "════════════════════════════════════════════"
echo ""
echo "  Dashboard: http://$(hostname -I | awk '{print $1}'):8001/"
echo "  API docs:  http://$(hostname -I | awk '{print $1}'):8001/api/docs/"
echo "  Admin:     http://$(hostname -I | awk '{print $1}'):8001/admin/"
echo ""