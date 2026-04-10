#!/usr/bin/env python3
# ============================================================
# Registers AccountPerformance models and creates migration.
# Run ONCE: python apply_performance_migration.py
# ============================================================
import os, sys, subprocess

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
MODELS_PATH = 'apps/accounts/models.py'

with open(MODELS_PATH) as f:
    content = f.read()

# Add import of performance models at the bottom if not already there
IMPORT_LINE = 'from .performance_models import AccountPerformance, AccountPerformanceHistory'

if 'AccountPerformance' not in content:
    with open(MODELS_PATH, 'a') as f:
        f.write(f'\n\n# Phase 3c\n{IMPORT_LINE}\n')
    print(f'✅ Added AccountPerformance import to {MODELS_PATH}')
else:
    print('✅ AccountPerformance already imported')

# Run migrations
print('\nRunning makemigrations accounts...')
r1 = subprocess.run(
    [sys.executable, 'manage.py', 'makemigrations', 'accounts',
     '--name', 'add_account_performance'],
    capture_output=True, text=True
)
print(r1.stdout or '(no stdout)')
if r1.returncode != 0 and 'No changes' not in r1.stderr:
    print('STDERR:', r1.stderr[:400])

print('Running migrate...')
r2 = subprocess.run(
    [sys.executable, 'manage.py', 'migrate'],
    capture_output=True, text=True
)
print(r2.stdout or '(no stdout)')
if r2.returncode != 0:
    print('STDERR:', r2.stderr[:400])
else:
    print('✅ Migration complete')

# Verify
print('\nVerifying models...')
r3 = subprocess.run(
    [sys.executable, '-c', '''
import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from apps.accounts.performance_models import (
    AccountPerformance, AccountPerformanceHistory
)
print("  ✅ AccountPerformance")
print("  ✅ AccountPerformanceHistory")
fields = [f.name for f in AccountPerformance._meta.get_fields()]
for f in ["total_pips","total_profit","win_rate","profit_factor",
          "avg_rrr_used","max_drawdown_pct","symbol_stats"]:
    s = "✅" if f in fields else "❌"
    print(f"  {s} AccountPerformance.{f}")
'''],
    capture_output=True, text=True
)
print(r3.stdout)
if r3.returncode != 0:
    print('STDERR:', r3.stderr[:200])
print('\n✅ Phase 3c complete')