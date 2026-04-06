"""
Quick before/after comparison:
  - Reads OLD 15m trained results from checkpoint
  - Re-runs 15m trained with current (expanded-retrained) model
  - Saves + prints side-by-side table
"""
import copy
import json
from pathlib import Path

from athena.backtest.runner import AthenaBacktest, load_ohlcv_from_csv
from athena.config import ATHENA_CONFIG
from athena.data.sentiment import AthenaSentiment
from athena.features.engineer import AthenaEngineer

ROOT = Path("d:/Projects/Athena")
RESULTS_DIR = ROOT / "data/results"
MODEL_PATH_15M = ROOT / "athena/model/athena_brain_15m.pkl"
CSV_15M = ROOT / "data/raw/ohlcv/BTCUSDT_15m_2025_06.csv"

CHECKPOINT = RESULTS_DIR / "tf_ab_matrix_2025_06.json"
OUT_JSON = RESULTS_DIR / "backtest_15m_comparison.json"


def make_cfg(sentiment_on: bool, profile: str) -> dict:
    cfg = copy.deepcopy(ATHENA_CONFIG)
    cfg["symbols"] = ["BTC/USDT"]
    cfg["timeframe"] = "15m"
    cfg["runtime_timeframe"] = "15m"
    cfg["training_timeframe"] = "15m"
    cfg["flags"]["SENTIMENT_ENABLED"] = sentiment_on
    cfg["flags"]["SENTIMENT_BACKTEST"] = sentiment_on
    cfg["flags"]["MTF_FILTER_ENABLED"] = False
    cfg["data"]["lookback_candles"] = 200
    cfg["model_path"] = str(MODEL_PATH_15M).replace("\\", "/")
    if profile == "conservative":
        cfg["risk"]["max_position_pct"] = 0.01
        cfg["risk"]["min_confidence"] = 0.55
        cfg["risk"]["stop_loss_pct"] = 0.0025
        cfg["risk"]["take_profit_pct"] = 0.0050
    elif profile == "aggressive":
        cfg["risk"]["max_position_pct"] = 0.03
        cfg["risk"]["min_confidence"] = 0.35
        cfg["risk"]["stop_loss_pct"] = 0.0040
        cfg["risk"]["take_profit_pct"] = 0.0100
    return cfg


def run_case(sentiment_on: bool, profile: str) -> dict:
    cfg = make_cfg(sentiment_on=sentiment_on, profile=profile)
    engineer = AthenaEngineer(cfg)
    sentiment = AthenaSentiment(cfg)
    backtest = AthenaBacktest(engineer, sentiment, cfg)
    ohlcv = load_ohlcv_from_csv(str(CSV_15M), symbol=None, max_rows=1500, window="first")
    result = backtest.run(ohlcv, initial_balance=10_000.0, symbol="BTC/USDT")
    return result if result else {"total_trades": 0}


def fmt_delta(old_val, new_val, is_good_when_positive=True):
    delta = new_val - old_val
    sign = "+" if delta >= 0 else ""
    arrow = "UP" if (delta > 0) == is_good_when_positive else ("DOWN" if delta != 0 else "=")
    return f"{new_val:.4f} ({sign}{delta:.4f} {arrow})"


def print_table(case_key: str, old: dict, new: dict):
    print(f"\n{'='*60}")
    print(f"  Case: {case_key}")
    print(f"{'='*60}")
    metrics = [
        ("total_trades",     "Trades",   True),
        ("win_rate",         "Win Rate", True),
        ("total_return_pct", "Return%",  True),
        ("sharpe_ratio",     "Sharpe",   True),
        ("profit_factor",    "PF",       True),
        ("max_drawdown_pct", "MaxDD%",   False),
    ]
    print(f"  {'Metric':<20} {'Before':>14} {'After':>30}")
    print(f"  {'-'*20} {'-'*14} {'-'*30}")
    for key, label, positive_good in metrics:
        ov = float(old.get(key, 0.0) or 0.0)
        nv = float(new.get(key, 0.0) or 0.0)
        print(f"  {label:<20} {ov:>14.4f}   {fmt_delta(ov, nv, positive_good):>28}")


def main():
    # Load old checkpoint
    old_data = {}
    if CHECKPOINT.exists():
        try:
            old_data = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        except Exception:
            pass

    old_trained = old_data.get("15m", {}).get("trained", {})
    cases = [
        (True,  "conservative", "sent_on__conservative"),
        (True,  "aggressive",   "sent_on__aggressive"),
        (False, "conservative", "sent_off__conservative"),
        (False, "aggressive",   "sent_off__aggressive"),
    ]

    new_trained = {}
    for sentiment_on, profile, key in cases:
        print(f"Running: 15m trained | {key} ...")
        new_trained[key] = run_case(sentiment_on, profile)
        print(f"  -> trades={new_trained[key].get('total_trades')}, "
              f"win_rate={new_trained[key].get('win_rate',0):.3f}, "
              f"return%={new_trained[key].get('total_return_pct',0):.4f}")

    # Print comparison tables
    print("\n\n" + "="*60)
    print("  BEFORE vs AFTER (15m model, expanded retrain)")
    print("="*60)
    for sentiment_on, profile, key in cases:
        old = old_trained.get(key, {})
        new = new_trained[key]
        print_table(key, old, new)

    # Save
    comparison = {
        "before": old_trained,
        "after": new_trained,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved comparison: {OUT_JSON}")

    # Update main checkpoint with new trained results
    # Print comparison tables
    print("\n\n" + "="*60)
    print("  BEFORE vs AFTER (15m model, expanded retrain)")
    print("="*60)
    for sentiment_on, profile, key in cases:
        old = old_trained.get(key, {})
        new = new_trained[key]
        print_table(key, old, new)

    if "15m" in old_data:
        old_data["15m"]["trained"] = new_trained
        # Recompute delta
        delta = {}
        for key in new_trained:
            bl = old_data["15m"].get("baseline", {}).get(key, {})
            for metric in ["total_trades", "win_rate", "total_return_pct", "max_drawdown_pct", "sharpe_ratio", "profit_factor"]:
                delta.setdefault(key, {})[metric] = {
                    "baseline": float(bl.get(metric, 0.0) or 0.0),
                    "trained": float(new_trained[key].get(metric, 0.0) or 0.0),
                    "delta": float(new_trained[key].get(metric, 0.0) or 0.0) - float(bl.get(metric, 0.0) or 0.0),
                }
        old_data["15m"]["delta"] = delta
        CHECKPOINT.write_text(json.dumps(old_data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Updated checkpoint: {CHECKPOINT}")


if __name__ == "__main__":
    main()
