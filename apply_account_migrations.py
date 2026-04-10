#!/usr/bin/env python3
# ============================================================
# ABSOLUTE PATH: /opt/forex_bot/apply_account_migration.py
# Patches apps/accounts/models.py and runs migration.
# Run ONCE from project root:
#   python apply_account_migration.py
# ============================================================
import os, sys, subprocess, re

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
MODELS_PATH = 'apps/accounts/models.py'

with open(MODELS_PATH) as f:
    content = f.read()

changed = False

# ── Step 1: Add choice classes ────────────────────────────────
if 'BrokerType' not in content:
    CHOICES = '''
class BrokerType(models.TextChoices):
    OANDA = 'oanda', 'OANDA'
    MT5   = 'mt5',   'MetaTrader 5'
    OTHER = 'other', 'Other'


class AccountType(models.TextChoices):
    PERSONAL = 'personal', 'Personal'
    FUNDED   = 'funded',   'Funded Account'
    DEMO     = 'demo',     'Practice / Demo'
    CONTEST  = 'contest',  'Contest'


class FundedFirm(models.TextChoices):
    FTMO          = 'ftmo',          'FTMO'
    MFF           = 'mff',           'MyForexFunds'
    TRUE_FOREX    = 'true_forex',    'True Forex Funds'
    FUNDED_NEXT   = 'funded_next',   'FundedNext'
    ALPHA_CAPITAL = 'alpha_capital', 'Alpha Capital Group'
    E8_FUNDING    = 'e8_funding',    'E8 Funding'
    OTHER_FIRM    = 'other',         'Other'

'''
    # Insert before the first class definition
    first_class = re.search(r'^class \w', content, re.MULTILINE)
    if first_class:
        pos = first_class.start()
        content = content[:pos] + CHOICES + content[pos:]
        changed = True
        print("✅ Added BrokerType, AccountType, FundedFirm choices")
    else:
        print("⚠ Could not find insertion point — add choices manually")
else:
    print("✅ BrokerType already present — skipping")

# ── Step 2: Add new fields to TradingAccount ─────────────────
if 'broker_type' not in content:
    NEW_FIELDS = '''
    # ── Phase 3 additions ──────────────────────────────────────
    broker_type      = models.CharField(
        max_length=20, choices=BrokerType.choices,
        default=BrokerType.OANDA,
        help_text='Broker connector type',
    )
    account_type     = models.CharField(
        max_length=20, choices=AccountType.choices,
        default=AccountType.DEMO,
        help_text='Account category',
    )
    funded_firm      = models.CharField(
        max_length=30, choices=FundedFirm.choices,
        default='', blank=True,
        help_text='Funded firm (FTMO, MFF…) — blank for personal',
    )
    max_loss_limit   = models.FloatField(
        null=True, blank=True,
        help_text='Max loss allowed (USD) for funded accounts',
    )
    profit_target    = models.FloatField(
        null=True, blank=True,
        help_text='Profit target for funded challenge (USD)',
    )
    daily_loss_limit = models.FloatField(
        null=True, blank=True,
        help_text='Daily drawdown limit (USD)',
    )
'''
    # Insert after the `broker` field line
    target_patterns = [
        "    broker      =",
        "    broker =",
        "    broker=",
    ]
    inserted = False
    for pat in target_patterns:
        if pat in content:
            # Find end of that line
            idx  = content.index(pat)
            end  = content.index('\n', idx)
            # Skip to end of the field block (find next blank line or field)
            rest = content[end:]
            # Find next field definition or blank line
            next_field = re.search(r'\n    \w', rest)
            if next_field:
                insert_at = end + next_field.start()
                content   = content[:insert_at] + '\n' + NEW_FIELDS + content[insert_at:]
                inserted  = True
                changed   = True
                print("✅ Added broker_type, account_type, funded_firm fields")
                break
    if not inserted:
        # Fallback: append before Meta class
        if 'class Meta' in content:
            idx     = content.index('    class Meta')
            content = content[:idx] + NEW_FIELDS + '\n' + content[idx:]
            changed = True
            print("✅ Added fields before Meta class (fallback)")
        else:
            print("⚠ Could not find insertion point — add fields manually")
else:
    print("✅ broker_type already present — skipping")

# ── Write file ────────────────────────────────────────────────
if changed:
    # Verify syntax before writing
    import ast
    try:
        ast.parse(content)
    except SyntaxError as e:
        print(f"❌ SyntaxError in patched file at line {e.lineno}: {e.text}")
        print("   Aborting — file NOT written")
        sys.exit(1)

    with open(MODELS_PATH, 'w') as f:
        f.write(content)
    print(f"✅ {MODELS_PATH} updated")
else:
    print("ℹ No changes needed")

# ── Run migration ─────────────────────────────────────────────
print("\nRunning makemigrations accounts...")
r1 = subprocess.run(
    [sys.executable, 'manage.py', 'makemigrations', 'accounts',
     '--name', 'add_broker_type_account_type_funded'],
    capture_output=True, text=True
)
print(r1.stdout or "(no stdout)")
if r1.returncode != 0 and 'No changes' not in r1.stderr:
    print("STDERR:", r1.stderr[:400])

print("Running migrate...")
r2 = subprocess.run(
    [sys.executable, 'manage.py', 'migrate'],
    capture_output=True, text=True
)
print(r2.stdout or "(no stdout)")
if r2.returncode != 0:
    print("STDERR:", r2.stderr[:400])
else:
    print("✅ Migration complete")

# ── Verify ────────────────────────────────────────────────────
print("\nVerifying fields exist on model...")
r3 = subprocess.run(
    [sys.executable, '-c', '''
import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from apps.accounts.models import TradingAccount
fields = [f.name for f in TradingAccount._meta.get_fields()]
for f in ["broker_type","account_type","funded_firm","max_loss_limit",
          "profit_target","daily_loss_limit"]:
    status = "✅" if f in fields else "❌"
    print(f"  {status} {f}")
'''],
    capture_output=True, text=True
)
print(r3.stdout)
if r3.returncode != 0:
    print("STDERR:", r3.stderr[:200])

print("\n✅ Phase 3a complete — run test_performance_phase3.sh after 3b")