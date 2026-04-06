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
    else:
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


def delta_row(before: dict, after: dict, metric: str) -> dict:
    b = float(before.get(metric, 0.0) or 0.0)
    a = float(after.get(metric, 0.0) or 0.0)
    return {"baseline": b, "trained": a, "delta": a - b}


def main():
    old_data = {}
    if CHECKPOINT.exists():
        old_data = json.loads(CHECKPOINT.read_text(encoding="utf-8"))

    old_trained = old_data.get("15m", {}).get("trained", {})
    old_baseline = old_data.get("15m", {}).get("baseline", {})

    cases = [
        (True, "conservative", "sent_on__conservative"),
        (True, "aggressive", "sent_on__aggressive"),
        (False, "conservative", "sent_off__conservative"),
        (False, "aggressive", "sent_off__aggressive"),
    ]

    new_trained = {}
    for sentiment_on, profile, key in cases:
        print(f"run {key}")
        new_trained[key] = run_case(sentiment_on, profile)

    metrics = [
        "total_trades",
        "win_rate",
        "total_return_pct",
        "max_drawdown_pct",
        "sharpe_ratio",
        "profit_factor",
    ]
    delta = {}
    for _, _, key in cases:
        delta[key] = {m: delta_row(old_baseline.get(key, {}), new_trained[key], m) for m in metrics}

    comparison = {
        "before": old_trained,
        "after": new_trained,
        "delta_vs_baseline": delta,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")

    if "15m" in old_data:
        old_data["15m"]["trained"] = new_trained
        old_data["15m"]["delta"] = delta
        CHECKPOINT.write_text(json.dumps(old_data, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"saved {OUT_JSON}")


if __name__ == "__main__":
    main()
