from __future__ import annotations

from typing import Any, Dict, Iterable, Sequence

import pandas as pd

from athena.features.engineer import AthenaEngineer
from athena.model.fusion import SignalFusion


def confidence_bucket(confidence: float) -> str:
    value = float(confidence)
    if value < 0.45:
        return "0.00-0.45"
    if value < 0.55:
        return "0.45-0.55"
    if value < 0.65:
        return "0.55-0.65"
    return "0.65-1.00"


def regime_bucket(vol_regime: float) -> str:
    value = float(vol_regime)
    if value < 0.25:
        return "quiet"
    if value > 0.75:
        return "hot"
    return "normal"


def _metrics(frame: pd.DataFrame, signed_col: str) -> Dict[str, float]:
    if frame.empty:
        return {
            "count": 0,
            "win_rate": 0.0,
            "edge_per_signal": 0.0,
            "avg_confidence": 0.0,
        }

    signed = pd.to_numeric(frame[signed_col], errors="coerce").fillna(0.0)
    conf_source = frame["confidence"] if "confidence" in frame.columns else pd.Series(0.0, index=frame.index)
    conf = pd.to_numeric(conf_source, errors="coerce").fillna(0.0)
    return {
        "count": int(len(frame)),
        "win_rate": float((signed > 0).mean()),
        "edge_per_signal": float(signed.mean()),
        "avg_confidence": float(conf.mean()),
    }


def build_signal_records(
    ohlcv_data: Sequence[Sequence[float]],
    config: Dict,
    symbol: str = "BTC/USDT",
    exchange: str = "binance",
    horizons: Iterable[int] | None = None,
) -> pd.DataFrame:
    df = pd.DataFrame(
        ohlcv_data,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    ).astype(float)
    if df.empty:
        return pd.DataFrame()

    cfg = dict(config)
    engineer = AthenaEngineer(cfg)
    fusion = SignalFusion(cfg)

    horizon_values = sorted({max(1, int(h)) for h in (horizons or [cfg.get("training", {}).get("label_lookahead", 10)])})
    max_horizon = max(horizon_values)
    min_lookback = max(getattr(engineer, "windows", [120])) + 10
    desired_lookback = max(
        int(cfg.get("data", {}).get("lookback_candles", 200)),
        min_lookback,
    )
    max_available = len(df) - max_horizon - 1
    if max_available < min_lookback:
        return pd.DataFrame()
    lookback = max(min_lookback, min(desired_lookback, max_available))

    rows = []
    for i in range(lookback, len(df) - max_horizon):
        batch = {
            "ohlcv": df.iloc[i - lookback:i].values.tolist(),
            "orderbook": {},
            "symbol": symbol,
            "exchange": exchange,
        }
        features = engineer.transform(batch)
        if features is None:
            continue

        signal = fusion.predict(features, None)
        close = float(df["close"].iloc[i])
        ts = int(df["timestamp"].iloc[i])
        hour = int(pd.to_datetime(ts, unit="ms", utc=True).hour)
        vol = float(features.get("vol_regime", 0.5))

        row = {
            "timestamp": ts,
            "close": close,
            "direction": int(signal.direction),
            "confidence": float(signal.confidence),
            "vol_regime": vol,
            "regime_bucket": regime_bucket(vol),
            "hour": hour,
        }

        for horizon in horizon_values:
            future_close = float(df["close"].iloc[i + horizon])
            forward_return = (future_close - close) / max(close, 1e-9)
            row[f"forward_return_{horizon}"] = float(forward_return)
            row[f"signed_return_{horizon}"] = float(forward_return * int(signal.direction))

        rows.append(row)

    return pd.DataFrame(rows)


def summarize_signal_records(
    records: pd.DataFrame,
    primary_horizon: int = 10,
    min_confidence: float | None = None,
) -> Dict:
    if records.empty:
        return {
            "summary": {"total_rows": 0, "total_signals": 0, "edge_per_signal": 0.0},
            "confidence_breakdown": [],
            "side_breakdown": {},
            "regime_breakdown": {},
            "hour_breakdown": [],
        }

    signed_col = f"signed_return_{int(primary_horizon)}"
    if signed_col not in records.columns:
        signed_candidates = [c for c in records.columns if c.startswith("signed_return_")]
        if not signed_candidates:
            raise KeyError("No signed_return_* columns present in diagnostics records")
        signed_col = signed_candidates[0]

    frame = records.copy()
    if "regime_bucket" not in frame.columns and "vol_regime" in frame.columns:
        frame["regime_bucket"] = frame["vol_regime"].map(regime_bucket)
    frame["confidence_bin"] = frame["confidence"].map(confidence_bucket)
    frame["side"] = frame["direction"].map({1: "long", -1: "short"}).fillna("hold")

    directional = frame[frame["direction"] != 0].copy()

    summary: dict[str, Any] = dict(_metrics(directional, signed_col))
    summary.update(
        {
            "total_rows": int(len(frame)),
            "total_signals": int(len(directional)),
            "hold_count": int((frame["direction"] == 0).sum()),
            "hold_ratio": float((frame["direction"] == 0).mean()),
            "primary_horizon": int(primary_horizon),
        }
    )

    if min_confidence is not None:
        above = directional[directional["confidence"] >= float(min_confidence)]
        summary["above_threshold"] = _metrics(above, signed_col)
        summary["above_threshold"]["threshold"] = float(min_confidence)

    confidence_breakdown = []
    for bucket in ["0.00-0.45", "0.45-0.55", "0.55-0.65", "0.65-1.00"]:
        part = directional[directional["confidence_bin"] == bucket]
        row: dict[str, Any] = {"bucket": bucket}
        row.update(_metrics(part, signed_col))
        confidence_breakdown.append(row)

    side_breakdown = {}
    for side in ["long", "short"]:
        side_breakdown[side] = _metrics(directional[directional["side"] == side], signed_col)

    regime_breakdown = {}
    for bucket in ["quiet", "normal", "hot"]:
        regime_breakdown[bucket] = _metrics(directional[directional["regime_bucket"] == bucket], signed_col)

    hour_rows = []
    if "hour" in directional.columns:
        grouped = directional.groupby("hour", sort=True)
        for hour, part in grouped:
            hour_value = pd.to_numeric(pd.Series([hour]), errors="coerce").iloc[0]
            row: dict[str, Any] = {"hour": int(hour_value) if pd.notna(hour_value) else -1}
            row.update(_metrics(part, signed_col))
            hour_rows.append(row)

    return {
        "summary": summary,
        "confidence_breakdown": confidence_breakdown,
        "side_breakdown": side_breakdown,
        "regime_breakdown": regime_breakdown,
        "hour_breakdown": hour_rows,
    }
