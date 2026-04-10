#!/usr/bin/env python3
# ============================================================
# Adds performance URL to config/urls.py
# Run ONCE: python wire_performance_urls.py
# ============================================================
import ast, sys

path = 'config/urls.py'
with open(path) as f:
    content = f.read()

if 'performance_urlpatterns' in content:
    print('✅ Performance URLs already registered')
    sys.exit(0)

# Add import
old_import = 'from apps.accounts.portfolio_urls import portfolio_urlpatterns'
new_import  = (
    'from apps.accounts.performance_urls import performance_urlpatterns\n'
    + old_import
)
if old_import in content:
    content = content.replace(old_import, new_import)
else:
    # Fallback — add near other account imports
    old_import2 = 'from apps.trading.dashboard_views import'
    content = content.replace(
        old_import2,
        'from apps.accounts.performance_urls import performance_urlpatterns\n'
        + old_import2
    )

# Add URL path
old_path = "    path('api/v1/portfolios/',"
new_path  = (
    "    path('api/v1/performance/', "
    "include((performance_urlpatterns, 'performance'))),\n"
    + old_path
)
if old_path in content:
    content = content.replace(old_path, new_path)
else:
    old_path2 = "    path(API_V1 + 'auth/',"
    content = content.replace(
        old_path2,
        "    path('api/v1/performance/', "
        "include((performance_urlpatterns, 'performance'))),\n    "
        + old_path2.strip()
    )

try:
    ast.parse(content)
except SyntaxError as e:
    print(f'❌ SyntaxError at line {e.lineno}: {e.text}')
    sys.exit(1)

with open(path, 'w') as f:
    f.write(content)

print('✅ Performance URLs added to config/urls.py')
print('   Restart Daphne to activate.')