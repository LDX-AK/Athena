# QUICK REFERENCE: Athena 15m Model Status

**Last Updated**: April 6, 2026  
**Model**: Production-Ready ✅  
**Location**: `athena/model/athena_brain_15m.pkl` (2.66 MB)  

---

## 📊 Performance (6-Month Retrain)

| Config | Win Rate | Return | Sharpe | Status |
|--------|----------|--------|--------|--------|
| Sentiment OFF + Aggressive | 50.8% | **+0.42%** | 5.21 | 🏆 Best |
| Sentiment ON + Conservative | 73.2% | **+0.12%** | 10.38 | ⭐ Stable |
| Sentiment OFF + Conservative | 66.7% | **+0.27%** | 7.61 | ✅ Good |
| Sentiment ON + Aggressive | 44.4% | **+0.23%** | 3.21 | ✅ OK |

---

## 🐧 Deploy on Linux (3 Steps)

```bash
# 1. Setup
git clone https://github.com/LDX-AK/Athena.git
cd Athena && python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Scheduler (choose one)

# Option A: systemd (automatic, recommended)
sudo cp scripts/athena_15m_retrain.{service,timer} /etc/systemd/system/
sudo systemctl enable athena_15m_retrain.timer && sudo systemctl start athena_15m_retrain.timer

# Option B: cron (simple)
crontab -e  # add: 0 2 * * 0 /home/athena/Athena/scripts/cron_15m_retrain.sh

# 3. Test
python3 -m athena --mode paper --timeframe 15m  # Wait 30s, should show trades
```

---

## 📋 Monitoring Checklist

- [ ] Model file exists: `athena/model/athena_brain_15m.pkl` (2.66 MB)
- [ ] Scheduler active: `systemctl status athena_15m_retrain.timer` OR `crontab -l`
- [ ] First retrain completed: Check `data/results/train_15m_cron_*.log`
- [ ] Paper trading running: `python3 -m athena --mode paper --timeframe 15m`
- [ ] Backtest metrics: `python3 run_compare_15m_fast.py`

---

## 🔧 Common Commands

```bash
# Check model age/size
stat athena/model/athena_brain_15m.pkl

# View latest retrain log
tail -50 $(ls -t data/results/train_15m_cron_*.log | head -1)

# Run paper trading (15m only)
source .venv/bin/activate && python3 -m athena --mode paper --timeframe 15m

# Manual retrain
python3 train_model_tf.py --timeframe 15m --csv-path data/raw/ohlcv/BTCUSDT_15m_2025_01_06.csv --model-path athena/model/athena_brain_15m.pkl --max-rows 8000 --csv-window last

# View live stats
tail -f data/live_stats.json

# Check backtest results
python3 run_compare_15m_fast.py && cat data/results/backtest_15m_comparison.json | jq '.after'
```

---

## 📚 Documentation

- **Full Details**: `PRODUCTION_15M_README.md`
- **Linux Setup**: `LINUX_DEPLOYMENT.md`
- **Backtest Results**: `data/results/tf_ab_matrix_2025_06.json` (key: `"15m"`)

---

## 🐛 Troubleshooting

| Issue | Quick Fix |
|-------|-----------|
| Retrain not running | `sudo systemctl restart athena_15m_retrain.timer` |
| Paper mode hangs | `Ctrl+C`, check sentiment CSV exists |
| Model won't load | `pip install --force-reinstall lightgbm` |
| Low paper gains | Lower `min_confidence` to 0.40 in config.py |
| Scheduler disabled | `sudo systemctl enable athena_15m_retrain.timer` |

---

## 🎯 Next Steps

1. **Deploy on Linux** (follow 3-step guide above)
2. **Wait for first retrain** (Sunday 02:00 UTC)
3. **Monitor logs** and paper trading performance
4. **Iterate** if metrics degrade (reduce --max-rows, adjust config)

---

**GitHub**: https://github.com/LDX-AK/Athena (main branch, commits: 7149c7f latest)  
**Status**: ✅ Production Ready | 🚀 Auto-Retraining Enabled | 📈 Positive Performance
