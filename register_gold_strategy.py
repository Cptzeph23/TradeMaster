#!/usr/bin/env python3
# ============================================================
# Adds gold_xauusd to StrategyType enum + apps.py
# Run ONCE: python register_gold_strategy.py
# ============================================================
import os, sys, subprocess, ast

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# ── Step 1: Add to StrategyType enum in utils/constants.py ───
CONSTANTS_PATH = 'utils/constants.py'
with open(CONSTANTS_PATH) as f:
    content = f.read()

if 'gold_xauusd' not in content:
    # Find the ATR_BREAKOUT line and insert after it
    old = "    ATR_BREAKOUT   = 'atr_breakout',    'ATR Channel Breakout'"
    new = (old + "\n"
           "    GOLD_XAUUSD    = 'gold_xauusd',    'Gold XAUUSD'")
    if old in content:
        content = content.replace(old, new)
        with open(CONSTANTS_PATH, 'w') as f:
            f.write(content)
        print('✅ Added gold_xauusd to StrategyType enum')
    else:
        print('⚠ Could not find ATR_BREAKOUT line — add manually:')
        print("    GOLD_XAUUSD = 'gold_xauusd', 'Gold XAUUSD'")
else:
    print('✅ gold_xauusd already in StrategyType')

# ── Step 2: Register in apps/strategies/apps.py ──────────────
APPS_PATH = 'apps/strategies/apps.py'
with open(APPS_PATH) as f:
    apps_content = f.read()

if 'gold_xauusd' not in apps_content:
    old = "'.plugins.atr_breakout',"
    new = old + "\n            '.plugins.gold_xauusd',"
    if old in apps_content:
        apps_content = apps_content.replace(old, new)
        with open(APPS_PATH, 'w') as f:
            f.write(apps_content)
        print('✅ Registered gold_xauusd in apps/strategies/apps.py')
    else:
        print('⚠ Could not find atr_breakout in apps.py — add manually:')
        print("   '.plugins.gold_xauusd',")
else:
    print('✅ gold_xauusd already registered in apps.py')

# ── Step 3: Run migration (StrategyType choices changed) ──────
print('\nRunning makemigrations strategies...')
r1 = subprocess.run(
    [sys.executable, 'manage.py', 'makemigrations', 'strategies',
     '--name', 'add_gold_xauusd_strategy_type'],
    capture_output=True, text=True
)
print(r1.stdout or '(no stdout)')
if r1.returncode != 0 and 'No changes' not in r1.stderr:
    print('STDERR:', r1.stderr[:300])

r2 = subprocess.run(
    [sys.executable, 'manage.py', 'migrate'],
    capture_output=True, text=True
)
print(r2.stdout or '(no stdout)')
if r2.returncode != 0:
    print('STDERR:', r2.stderr[:300])
else:
    print('✅ Migration complete')

# ── Step 4: Verify ────────────────────────────────────────────
print('\nVerifying registration...')
r3 = subprocess.run(
    [sys.executable, '-c', '''
import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from apps.strategies.registry import StrategyRegistry
slugs = StrategyRegistry.list_slugs()
if "gold_xauusd" in slugs:
    cls = StrategyRegistry.get("gold_xauusd")
    print(f"  ✅ gold_xauusd registered → {cls.__name__}")
    print(f"  name:    {cls.name}")
    print(f"  version: {cls.version}")
else:
    print(f"  ❌ gold_xauusd not found. Registered: {slugs}")
'''],
    capture_output=True, text=True
)
print(r3.stdout)
if r3.returncode != 0:
    print('STDERR:', r3.stderr[:200])

print('\n✅ Phase 4a complete')