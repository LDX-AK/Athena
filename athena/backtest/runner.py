"""
athena/backtest/runner.py — AthenaBacktest v2

Улучшения vs v1:
  - Интеграция sentiment из CSV (Kaggle данные)
  - Multi-timeframe фильтр (1m + 15m)
  - Расширенные метрики: Calmar Ratio, Win Streak
  - Отчёт по месяцам для анализа сезонности
"""

import numpy as np
import pandas as pd
import logging
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from typing import List, Dict, Optional
from athena.features.engineer import AthenaEngineer
from athena.model.signal import AthenaModel, AthenaSignal
from athena.model.fusion import SignalFusion, SentimentSignal
from athena.data.sentiment import AthenaSentiment
from athena.filters.mtf_gate import MTFGate
from athena.filters.regime_router import RegimeRouter
from athena.risk.adaptive_mode import AdaptiveModeController
from athena.strategy.prototypes import RoutePrototypeEngine

logger = logging.getLogger("athena.backtest")


def load_ohlcv_from_csv(csv_path: str,
                        symbol: Optional[str] = None,
                        max_rows: Optional[int] = None,
                        window: Literal["first", "last"] = "last") -> List[List[float]]:
    """Load external OHLCV CSV files, including CryptoDataDownload minute exports."""
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        first_line = fh.readline().strip()
    skiprows = 1 if first_line.startswith("http") else 0

    header = pd.read_csv(path, skiprows=skiprows, nrows=0)
    header_cols = list(header.columns)

    candidates = {
        "timestamp": ["unix", "timestamp", "Timestamp", "time", "Time", "date", "Date"],
        "symbol": ["symbol", "Symbol", "pair", "Pair"],
        "open": ["open", "Open"],
        "high": ["high", "High"],
        "low": ["low", "Low"],
        "close": ["close", "Close"],
        "volume": ["Volume BTC", "volume", "Volume", "vol", "base_volume"],
    }

    resolved = {}
    for target, options in candidates.items():
        for option in options:
            if option in header_cols:
                resolved[target] = option
                break

    missing = [key for key in ("timestamp", "open", "high", "low", "close", "volume") if key not in resolved]
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")

    usecols = [resolved[k] for k in ["timestamp", "open", "high", "low", "close", "volume"]]
    if "symbol" in resolved:
        usecols.append(resolved["symbol"])
    usecols = list(dict.fromkeys(usecols))

    chunks = []
    total_rows = 0
    chunksize = 100_000
    symbol_col = resolved.get("symbol")

    reader = pd.read_csv(path, skiprows=skiprows, usecols=usecols, chunksize=chunksize)
    for chunk in reader:
        if symbol and symbol_col:
            chunk = chunk[chunk[symbol_col].astype(str) == symbol]
        if chunk.empty:
            continue

        if not max_rows:
            chunks.append(chunk)
            continue

        if window == "first":
            remain = max_rows - total_rows
            if remain <= 0:
                break
            take = chunk.iloc[:remain]
            if not take.empty:
                chunks.append(take)
                total_rows += len(take)
            if total_rows >= max_rows:
                break
        else:
            chunks.append(chunk)
            total_rows += len(chunk)
            while total_rows > max_rows and chunks:
                overflow = total_rows - max_rows
                first_chunk = chunks[0]
                if overflow >= len(first_chunk):
                    total_rows -= len(first_chunk)
                    chunks.pop(0)
                else:
                    chunks[0] = first_chunk.iloc[overflow:]
                    total_rows -= overflow

    if not chunks:
        raise ValueError(f"No OHLCV rows loaded from CSV: {path}")

    df = pd.concat(chunks, ignore_index=True)

    if symbol and symbol_col and df.empty:
        raise ValueError(f"CSV does not contain requested symbol: {symbol}")

    out = pd.DataFrame({
        "timestamp": df[resolved["timestamp"]],
        "open": df[resolved["open"]],
        "high": df[resolved["high"]],
        "low": df[resolved["low"]],
        "close": df[resolved["close"]],
        "volume": df[resolved["volume"]],
    }).dropna()

    if pd.api.types.is_numeric_dtype(out["timestamp"]):
        out["timestamp"] = pd.to_numeric(out["timestamp"], errors="coerce")
        if out["timestamp"].dropna().max() < 1_000_000_000_000:
            out["timestamp"] = out["timestamp"] * 1000
    else:
        out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True).astype("int64") // 1_000_000

    for col in ["open", "high", "low", "close", "volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.dropna().sort_values("timestamp").drop_duplicates(subset=["timestamp"])

    logger.info(
        "📂 CSV loaded: %s candles from %s (window=%s, max_rows=%s)",
        len(out),
        path,
        window,
        max_rows if max_rows is not None else "all",
    )
    return out[["timestamp", "open", "high", "low", "close", "volume"]].values.tolist()


class AthenaBacktest:
    def __init__(self, engineer: AthenaEngineer,
                 sentiment: AthenaSentiment,
                 config: Dict):
        self.engineer  = engineer
        self.sentiment = sentiment
        self.config    = config
        self.flags     = config.get("flags", {})
        self.fusion    = SignalFusion(config)
        self.mtf_gate  = MTFGate(config)
        self.regime_router = RegimeRouter(config)
        self.route_prototypes = RoutePrototypeEngine(config)
        self.router_enabled = bool(config.get("router", {}).get("enabled", False))

    def _sentiment_macro_gate_allows(self, direction: int, sentiment: Optional[Dict]) -> tuple[bool, str]:
        sent_cfg = self.config.get("sentiment", {})
        if not self.flags.get("SENTIMENT_ENABLED", True):
            return True, "sentiment-disabled"
        if str(sent_cfg.get("mode", "weighted")) != "macro_gate":
            return True, "sentiment-weighted"
        if direction == 0:
            return False, "hold"

        neutral_policy = str(sent_cfg.get("macro_neutral_policy", "pass"))
        if not sentiment:
            return neutral_policy != "block", "sentiment-missing"

        combined = float(sentiment.get("score", 0.0)) * 0.7 + float(sentiment.get("trend", 0.0)) * 0.3
        buy_threshold = float(sent_cfg.get("macro_buy_threshold", 0.08))
        sell_threshold = float(sent_cfg.get("macro_sell_threshold", -0.08))

        if direction > 0 and combined >= buy_threshold:
            return True, f"macro-long:{combined:.3f}"
        if direction < 0 and combined <= sell_threshold:
            return True, f"macro-short:{combined:.3f}"

        if neutral_policy == "block":
            return False, f"macro-block:{combined:.3f}"
        if direction > 0:
            return combined >= 0.0, f"macro-soft-long:{combined:.3f}"
        return combined <= 0.0, f"macro-soft-short:{combined:.3f}"

    def run(self, ohlcv_data: List,
            initial_balance: float = 10_000.0,
            symbol: str = "BTC/USDT") -> Dict:

        df = pd.DataFrame(
            ohlcv_data,
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        ).astype(float)

        risk_cfg = dict(self.config["risk"])
        comm = 0.0004
        lookback = max(
            int(self.config.get("data", {}).get("lookback_candles", 200)),
            max(getattr(self.engineer, "windows", [120])) + 10,
        )

        balance, trades = initial_balance, []
        in_pos = False
        entry = sl = tp = direction = 0
        position_size = 0.0
        entry_route = None
        entry_route_reason = None
        entry_session = None
        entry_regime = None
        router_history = []
        route_counts: Dict[str, int] = {}
        last_route_reason = ""

        adaptive = AdaptiveModeController(self.config)
        mode_history = []
        if adaptive.enabled:
            risk_proxy = SimpleNamespace(cfg=risk_cfg)
            for key, value in risk_cfg.items():
                setattr(risk_proxy, key, value)
            adaptive.set_risk_manager(risk_proxy)

        use_sentiment = (
            self.flags.get("SENTIMENT_ENABLED", True) and
            self.flags.get("SENTIMENT_BACKTEST", True)
        )

        logger.info(
            f"📈 Бэктест: {len(df)} свечей | "
            f"Sentiment: {'ON' if use_sentiment else 'OFF'} | "
            f"Adaptive: {'ON' if adaptive.enabled else 'OFF'} | "
            f"Symbol: {symbol}"
        )

        for i in range(lookback, len(df)):
            ts  = int(df["timestamp"].iloc[i])
            lo  = df["low"].iloc[i]
            hi  = df["high"].iloc[i]
            cl  = df["close"].iloc[i]

            # ── Проверяем SL/TP открытой позиции ──────────────
            if in_pos:
                hit_sl = (direction == 1 and lo <= sl) or (direction == -1 and hi >= sl)
                hit_tp = (direction == 1 and hi >= tp) or (direction == -1 and lo <= tp)

                if hit_sl or hit_tp:
                    ex_price = sl if hit_sl else tp
                    sz       = position_size
                    pnl      = (ex_price - entry) / entry * sz * direction
                    pnl     -= sz * comm * 2
                    balance += pnl
                    trades.append({
                        "pnl":       pnl,
                        "result":    "TP" if hit_tp else "SL",
                        "balance":   balance,
                        "timestamp": ts,
                        "entry":     entry,
                        "exit":      ex_price,
                        "direction": direction,
                        "route":     entry_route,
                        "route_reason": entry_route_reason,
                        "session":   entry_session,
                        "regime":    entry_regime,
                    })
                    in_pos = False
                    position_size = 0.0
                    entry_route = None
                    entry_route_reason = None
                    entry_session = None
                    entry_regime = None

            # ── Ищем новый сигнал ──────────────────────────────
            if not in_pos:
                batch = {
                    "ohlcv":     df.iloc[i - lookback:i].values.tolist(),
                    "orderbook": {},
                    "symbol":    symbol,
                    "exchange":  "binance",
                }

                if adaptive.enabled:
                    new_mode = adaptive.update(
                        i - lookback,
                        {"ohlcv": batch["ohlcv"], "recent_trades": trades},
                    )
                    if new_mode is not None:
                        mode_history.append({
                            "bar_index": i - lookback,
                            "mode": new_mode.value,
                            "reason": adaptive.last_reason,
                        })

                # Добавляем sentiment из CSV если включён
                sent_data = {}
                if use_sentiment:
                    sent_data = self.sentiment.get_historical(symbol, ts)
                    batch["sentiment"] = sent_data

                features = self.engineer.transform(batch)
                if features is None:
                    continue

                sl_pct = float(risk_cfg["stop_loss_pct"])
                tp_pct = float(risk_cfg["take_profit_pct"])
                pos_pct = float(risk_cfg["max_position_pct"])
                min_conf = float(risk_cfg["min_confidence"])

                signal = self.fusion.predict(features, sent_data if use_sentiment else None)
                mtf_ok, _ = self.mtf_gate.allow_signal(batch["ohlcv"], signal.direction)
                sentiment_ok, _ = self._sentiment_macro_gate_allows(
                    signal.direction,
                    sent_data if use_sentiment else None,
                )

                prototype_name = None
                if self.router_enabled:
                    route_decision = self.regime_router.decide(
                        features,
                        timestamp_ms=ts,
                        raw_confidence=signal.confidence,
                    )
                    current_regime = str(route_decision.get("regime", "normal"))
                    current_session = str(route_decision.get("session", "unknown"))
                    route_name = str(route_decision.get("route", "directional"))
                    route_reason = str(route_decision.get("reason", ""))
                    adjusted_confidence = float(route_decision.get("adjusted_confidence", signal.confidence))

                    prototype_decision = self.route_prototypes.apply(route_name, features)
                    if prototype_decision is not None:
                        prototype_name = prototype_decision.name
                        route_reason = f"{route_reason} | {prototype_decision.reason}"
                        if prototype_decision.direction == 0:
                            signal = AthenaSignal(0, 0.0, signal.symbol, signal.exchange, signal.price, signal.features)
                            adjusted_confidence = 0.0
                        else:
                            signal = AthenaSignal(
                                direction=prototype_decision.direction,
                                confidence=float(prototype_decision.confidence),
                                symbol=signal.symbol,
                                exchange=signal.exchange,
                                price=signal.price,
                                features=signal.features,
                            )
                            adjusted_confidence = float(signal.confidence)

                    last_route_reason = route_reason
                    route_counts[route_name] = route_counts.get(route_name, 0) + 1
                    max_router_history = int(self.config.get("router", {}).get("max_history", 200))
                    if len(router_history) < max_router_history:
                        router_history.append({
                            "timestamp": ts,
                            "route": route_name,
                            "regime": current_regime,
                            "session": current_session,
                            "reason": route_reason,
                            "prototype": prototype_name,
                            "raw_confidence": float(signal.confidence),
                            "adjusted_confidence": adjusted_confidence,
                        })
                else:
                    vol_regime = float(features.get("vol_regime", 0.5))
                    current_regime = "quiet" if vol_regime < 0.25 else ("hot" if vol_regime > 0.75 else "normal")
                    current_session = "disabled"
                    route_name = "disabled"
                    route_reason = "router-disabled"
                    adjusted_confidence = float(signal.confidence)

                exp_cfg = self.config.get("experiment", {})
                direction_filter = str(exp_cfg.get("direction_filter", "both")).strip().lower()
                regime_filter = str(exp_cfg.get("regime_filter", "all")).strip().lower()
                meta_cfg = dict(exp_cfg.get("meta_filter", {}) or {})
                current_hour = int(features.get(
                    "hour_bucket",
                    datetime.fromtimestamp(float(ts) / 1000.0, tz=timezone.utc).hour,
                ))
                direction_ok = (
                    direction_filter == "both"
                    or (direction_filter == "long" and signal.direction > 0)
                    or (direction_filter == "short" and signal.direction < 0)
                )
                regime_ok = regime_filter in {"all", current_regime}
                route_ok = (not self.router_enabled) or route_name != "no_trade"

                allowed_hours = {
                    int(hour) % 24
                    for hour in meta_cfg.get("allowed_hours", [])
                    if str(hour).strip() != ""
                }
                allowed_regimes = {
                    str(name).strip().lower()
                    for name in meta_cfg.get("allowed_regimes", [])
                    if str(name).strip()
                }
                meta_min_conf = meta_cfg.get("min_confidence")
                meta_max_conf = meta_cfg.get("max_confidence")
                hour_ok = not allowed_hours or current_hour in allowed_hours
                meta_regime_ok = not allowed_regimes or current_regime in allowed_regimes
                meta_conf_ok = (
                    (meta_min_conf is None or adjusted_confidence >= float(meta_min_conf))
                    and (meta_max_conf is None or adjusted_confidence <= float(meta_max_conf))
                )

                if (
                    signal.direction != 0
                    and route_ok
                    and direction_ok
                    and regime_ok
                    and hour_ok
                    and meta_regime_ok
                    and meta_conf_ok
                    and adjusted_confidence >= min_conf
                    and mtf_ok
                    and sentiment_ok
                ):
                    entry, direction = cl, signal.direction
                    position_size = balance * pos_pct
                    sl = entry * (1 - sl_pct) if direction == 1 else entry * (1 + sl_pct)
                    tp = entry * (1 + tp_pct) if direction == 1 else entry * (1 - tp_pct)
                    entry_route = route_name
                    entry_route_reason = route_reason
                    entry_session = current_session
                    entry_regime = current_regime
                    in_pos = True

        adaptive_summary = None
        if adaptive.enabled:
            adaptive_summary = adaptive.summary()
            adaptive_summary["history"] = mode_history

        router_summary = {
            "enabled": self.router_enabled,
            "route_counts": route_counts,
            "last_route_reason": last_route_reason,
            "history": router_history[-50:],
        }

        return self._report(
            trades,
            initial_balance,
            balance,
            df,
            adaptive_summary=adaptive_summary,
            router_summary=router_summary,
        )

    def _report(self, trades: List[Dict], init: float,
                final: float, df: pd.DataFrame,
                adaptive_summary: Optional[Dict] = None,
                router_summary: Optional[Dict] = None) -> Dict:
        if not trades:
            logger.warning("Нет сделок в бэктесте")
            return {}

        pnls   = [t["pnl"] for t in trades]
        wins   = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        bals   = [t["balance"] for t in trades]

        # Max Drawdown
        peak, mdd = init, 0.0
        for b in bals:
            peak = max(peak, b)
            mdd  = max(mdd, (peak - b) / peak)

        # Sharpe
        s      = pd.Series(pnls)
        sharpe = (s.mean() / s.std() * np.sqrt(252)) if s.std() > 0 else 0

        # Calmar Ratio = Annual Return / Max Drawdown
        ret    = (final - init) / init
        calmar = (ret / (mdd + 1e-9))

        # Profit Factor
        pf = sum(wins) / abs(sum(losses)) if losses else float("inf")

        # Win Streak
        max_win_streak  = 0
        max_loss_streak = 0
        cur_streak = 0
        for p in pnls:
            if p > 0:
                cur_streak = cur_streak + 1 if cur_streak > 0 else 1
                max_win_streak = max(max_win_streak, cur_streak)
            else:
                cur_streak = cur_streak - 1 if cur_streak < 0 else -1
                max_loss_streak = max(max_loss_streak, abs(cur_streak))

        m = {
            "total_trades":       len(trades),
            "win_rate":           len(wins) / len(trades),
            "total_return_pct":   ret * 100,
            "final_balance":      final,
            "max_drawdown_pct":   mdd * 100,
            "sharpe_ratio":       sharpe,
            "calmar_ratio":       calmar,
            "profit_factor":      pf,
            "avg_win":            np.mean(wins)   if wins   else 0,
            "avg_loss":           np.mean(losses) if losses else 0,
            "max_win_streak":     max_win_streak,
            "max_loss_streak":    max_loss_streak,
            "best_trade":         max(pnls),
            "worst_trade":        min(pnls),
        }
        if adaptive_summary:
            m["adaptive_mode"] = adaptive_summary
        if router_summary:
            m["router"] = router_summary

        self._print_report(m)
        return m

    def _print_report(self, m: Dict):
        print("\n" + "━" * 56)
        print("  ⚡ ATHENA AI-BOT v2  |  BACKTEST RESULTS")
        print("━" * 56)
        print(f"  Сделок:            {m['total_trades']}")
        print(f"  Win Rate:          {m['win_rate']*100:.1f}%")
        print(f"  Общий доход:       {m['total_return_pct']:+.2f}%")
        print(f"  Финал. баланс:     ${m['final_balance']:.2f}")
        print(f"  Max Drawdown:      {m['max_drawdown_pct']:.2f}%")
        print(f"  Sharpe Ratio:      {m['sharpe_ratio']:.2f}")
        print(f"  Calmar Ratio:      {m['calmar_ratio']:.2f}")
        print(f"  Profit Factor:     {m['profit_factor']:.2f}")
        print(f"  Avg Win:           ${m['avg_win']:.2f}")
        print(f"  Avg Loss:          ${m['avg_loss']:.2f}")
        print(f"  Макс. серия побед: {m['max_win_streak']}")
        print(f"  Макс. серия потерь:{m['max_loss_streak']}")
        if m.get("adaptive_mode", {}).get("enabled"):
            adaptive = m["adaptive_mode"]
            print(
                f"  Adaptive Mode:     {adaptive.get('current_mode', 'n/a')} "
                f"| switches={adaptive.get('switch_count', 0)}"
            )
        router = m.get("router", {}) or {}
        if router.get("route_counts"):
            print(f"  Router routes:     {router.get('route_counts', {})}")
            if router.get("last_route_reason"):
                print(f"  Last route reason: {router.get('last_route_reason')}")
        print("━" * 56)

        ok = (m["sharpe_ratio"]  > 1.5 and
              m["max_drawdown_pct"] < 20 and
              m["profit_factor"] > 1.5 and
              m["calmar_ratio"]  > 0.5)

        if ok:
            print("  ✅ Стратегия перспективна → paper trading!")
        else:
            issues = []
            if m["sharpe_ratio"]    <= 1.5: issues.append(f"Sharpe={m['sharpe_ratio']:.2f}<1.5")
            if m["max_drawdown_pct"] >= 20:  issues.append(f"DD={m['max_drawdown_pct']:.1f}%>20%")
            if m["profit_factor"]   <= 1.5: issues.append(f"PF={m['profit_factor']:.2f}<1.5")
            if m["calmar_ratio"]    <= 0.5: issues.append(f"Calmar={m['calmar_ratio']:.2f}<0.5")
            print(f"  ⚠️  Нужна доработка: {', '.join(issues)}")
        print()
