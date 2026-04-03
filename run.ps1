param(
    [ValidateSet("train", "backtest", "paper", "live", "train_rl", "smoke-imports", "smoke-athena", "tests")]
    [string]$Mode = "paper"
)

$python = "d:/Projects/Athena/.venv/Scripts/python.exe"

if (-not (Test-Path $python)) {
    Write-Error ".venv python not found at $python"
    exit 1
}

switch ($Mode) {
    "smoke-imports" { & $python "test_imports.py"; break }
    "smoke-athena"  { & $python "test_athena_smoke.py"; break }
    "tests"         { & $python -m unittest discover -s tests -p "test_*.py" -v; break }
    default          { & $python -m athena --mode $Mode; break }
}

exit $LASTEXITCODE
