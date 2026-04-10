import os, sys, subprocess, re, ast
 
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
MODELS_PATH = 'apps/trading/models.py'
 
with open(MODELS_PATH) as f:
    content = f.read()
 
changed = False
 
NEW_FIELDS = '''
    # ── Phase 3: Pip + RRR tracking ───────────────────────────
    sl_pips          = models.FloatField(
        null=True, blank=True,
        help_text='Stop loss distance in pips at entry',
    )
    tp_pips          = models.FloatField(
        null=True, blank=True,
        help_text='Take profit distance in pips at entry',
    )
    profit_pips      = models.FloatField(
        null=True, blank=True,
        help_text='Actual pips gained (positive) or lost (negative)',
    )
    rrr_used         = models.FloatField(
        null=True, blank=True,
        help_text='Risk:Reward ratio used at entry (e.g. 2.0 = 1:2)',
    )
    rrr_achieved     = models.FloatField(
        null=True, blank=True,
        help_text='Actual RRR achieved at close',
    )
    account_label    = models.CharField(
        max_length=100, blank=True, default='',
        help_text='Human-readable account name for display/alerts',
    )
'''
 
if 'profit_pips' not in content:
    # Find insertion point: after profit_loss field or before status field
    insertion_patterns = [
        '    profit_loss',
        '    pnl',
        '    status',
    ]
    inserted = False
    for pat in insertion_patterns:
        if pat in content:
            idx  = content.index(pat)
            # Find end of this field block (next blank line)
            rest = content[idx:]
            nxt  = re.search(r'\n\n', rest)
            if nxt:
                insert_at = idx + nxt.start()
                content   = content[:insert_at] + '\n' + NEW_FIELDS + content[insert_at:]
                inserted  = True
                changed   = True
                print(f"✅ Inserted pip/RRR fields after '{pat.strip()}'")
                break
    if not inserted:
        # Fallback: insert before Meta class
        if '    class Meta' in content:
            idx     = content.index('    class Meta')
            content = content[:idx] + NEW_FIELDS + '\n' + content[idx:]
            changed = True
            print("✅ Added pip/RRR fields before Meta (fallback)")
        else:
            print("⚠ Could not find insertion point — add fields manually")
            print("Add to Trade model:")
            print(NEW_FIELDS)
else:
    print("✅ profit_pips already present — skipping")
 
if changed:
    try:
        ast.parse(content)
    except SyntaxError as e:
        print(f"❌ SyntaxError at line {e.lineno}: {e.text}")
        print("   File NOT written")
        sys.exit(1)
 
    with open(MODELS_PATH, 'w') as f:
        f.write(content)
    print(f"✅ {MODELS_PATH} updated")
 
# ── Migration ─────────────────────────────────────────────────
print("\nRunning makemigrations trading...")
r1 = subprocess.run(
    [sys.executable, 'manage.py', 'makemigrations', 'trading',
     '--name', 'add_pip_rrr_tracking_fields'],
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
print("\nVerifying fields on Trade model...")
r3 = subprocess.run(
    [sys.executable, '-c', '''
import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from apps.trading.models import Trade
fields = [f.name for f in Trade._meta.get_fields()]
for f in ["sl_pips","tp_pips","profit_pips","rrr_used",
          "rrr_achieved","account_label"]:
    status = "✅" if f in fields else "❌"
    print(f"  {status} {f}")
'''],
    capture_output=True, text=True
)
print(r3.stdout)
if r3.returncode != 0:
    print("STDERR:", r3.stderr[:200])
 
print("\n✅ Phase 3b complete")
 