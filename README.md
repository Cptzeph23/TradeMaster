# Forex Trading Bot Platform

Production-grade automated forex trading system with AI natural language command interface.

## Tech Stack
- **Backend**: Django 5.0 + Django REST Framework
- **Database**: PostgreSQL 15
- **Cache / Broker**: Redis 7
- **Async Workers**: Celery + Django-Celery-Beat
- **WebSockets**: Django Channels + Daphne
- **AI Commands**: Anthropic Claude (natural language → trading actions)
- **Brokers**: OANDA, MetaTrader 5
- **Analysis**: pandas, numpy, ta, vectorbt

## Phase Build Plan
- [x] Phase A — Project Scaffolding
- [ ] Phase B — Database Models
- [ ] Phase C — Authentication & Accounts
- [ ] Phase D — Strategy Engine
- [ ] Phase E — Market Data Layer
- [ ] Phase F — Trading Engine
- [ ] Phase G — Risk Management
- [ ] Phase H — Backtesting Engine
- [ ] Phase I — Celery Workers & Scheduler
- [ ] Phase J — REST API Layer
- [ ] Phase K — NLP Command Interface
- [ ] Phase L — WebSocket / Realtime
- [ ] Phase M — Web Dashboard
- [ ] Phase N — Security Hardening
- [ ] Phase O — Deployment

## Quick Start (after Phase O)
```bash
# 1. Clone and setup
git clone <repo> /opt/forex_bot
cd /opt/forex_bot

# 2. Run server setup
bash setup_server.sh

# 3. Configure environment
cp .env.example .env
nano .env

# 4. Install dependencies
source /opt/forex_bot_venv/bin/activate
pip install -r requirements.txt

# 5. Database setup
python manage.py migrate
python manage.py createsuperuser

# 6. Run development server
python manage.py runserver

# 7. Start Celery worker
celery -A config.celery worker -Q trading,orders,data,commands --loglevel=info
```

## Project Structure
See /docs/architecture.md (generated in Phase A)