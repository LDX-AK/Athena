#!/usr/bin/env python3
"""Quick smoke-test of all package imports."""
import sys

test_imports = [
    'ccxt', 'lightgbm', 'pandas', 'numpy', 
    'sklearn', 'loguru', 'dotenv', 'aiohttp', 
    'vaderSentiment', 'redis', 'streamlit'
]

ok = 0
err = []

for m in test_imports:
    try:
        __import__(m)
        print(f'  ✓ {m}')
        ok += 1
    except Exception as e:
        print(f'  ✗ {m}: {str(e)[:50]}')
        err.append(m)

print(f'\n=== Result: {ok}/{len(test_imports)} imports OK ===')

if err:
    print(f'Failed: {", ".join(err)}')
    sys.exit(1)
else:
    print('All core imports successful!')
    sys.exit(0)
