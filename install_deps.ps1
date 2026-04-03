$python = "D:\Projects\Athena\.venv\Scripts\python.exe"
Write-Host "=== Installing core deps ===" -ForegroundColor Cyan

& $python -m pip install -q ccxt aiohttp python-dotenv lightgbm scikit-learn vaderSentiment redis requests
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR on core deps" -ForegroundColor Red; exit 1 }

Write-Host "=== Installing streamlit (no-deps to skip pyarrow) ===" -ForegroundColor Cyan
& $python -m pip install -q streamlit --no-deps
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR on streamlit" -ForegroundColor Red; exit 1 }

Write-Host "=== Verification ===" -ForegroundColor Cyan
& $python -c "import numpy, pandas, ccxt, aiohttp, dotenv, lightgbm, sklearn, vaderSentiment, redis, requests, streamlit; print('ALL OK')"
Write-Host "Done!" -ForegroundColor Green
