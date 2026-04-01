# Athena AI-Bot v2.0

Hybrid crypto scalping bot with modular architecture.

## Core Stack
- LightGBM signal model
- Optional sentiment overlay (Kaggle CSV + CryptoPanic live)
- Optional PPO RL risk shield
- Multi-exchange data/execution pipeline

## Structure
- athena/core.py
- athena/config.py
- athena/data/fetcher.py
- athena/data/sentiment.py
- athena/features/engineer.py
- athena/model/signal.py
- athena/model/fusion.py
- athena/model/rl_shield.py
- athena/risk/manager.py
- athena/execution/router.py
- athena/backtest/runner.py
- athena/monitor/dashboard.py
- athena/monitor/streamlit_app.py

## Quick Start
1. Create virtual environment and install dependencies.
2. Copy `.env.example` to `.env` and set credentials.
3. Run Athena:

```powershell
python -m athena --mode train
python -m athena --mode backtest
python -m athena --mode paper
```

## Notes
- `files2` is used as the v2.0 source baseline.
- Missing modules were merged from `files1` where needed.
- RL and live sentiment are disabled by default in config flags.