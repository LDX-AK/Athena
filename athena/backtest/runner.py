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
from pathlib import Path
from typing import Literal
from typing import List, Dict, Optional
from athena.features.engineer import AthenaEngineer
from athena.model.signal import AthenaModel
from athena.model.fusion import SignalFusion, SentimentSignal
from athena.data.sentiment import AthenaSentiment
from athena.filters.mtf_gate import MTFGate

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

    def run(self, ohlcv_data: List,
            initial_balance: float = 10_000.0,
            symbol: str = "BTC/USDT") -> Dict:

        df = pd.DataFrame(
            ohlcv_data,
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        ).astype(float)

        sl_pct   = self.config["risk"]["stop_loss_pct"]
        tp_pct   = self.config["risk"]["take_profit_pct"]
        pos_pct  = self.config["risk"]["max_position_pct"]
        min_conf = self.config["risk"]["min_confidence"]
        comm     = 0.0004
        lookback = max(
            int(self.config.get("data", {}).get("lookback_candles", 200)),
            max(getattr(self.engineer, "windows", [120])) + 10,
        )

        balance, trades = initial_balance, []
        in_pos = False
        entry = sl = tp = direction = 0

        use_sentiment = (
            self.flags.get("SENTIMENT_ENABLED", True) and
            self.flags.get("SENTIMENT_BACKTEST", True)
        )

        logger.info(
            f"📈 Бэктест: {len(df)} свечей | "
            f"Sentiment: {'ON' if use_sentiment else 'OFF'} | "
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
                    sz       = balance * pos_pct
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
                    })
                    in_pos = False

            # ── Ищем новый сигнал ──────────────────────────────
            if not in_pos:
                batch = {
                    "ohlcv":     df.iloc[i - lookback:i].values.tolist(),
                    "orderbook": {},
                    "symbol":    symbol,
                    "exchange":  "binance",
                }

                # Добавляем sentiment из CSV если включён
                sent_data = {}
                if use_sentiment:
                    sent_data = self.sentiment.get_historical(symbol, ts)
                    batch["sentiment"] = sent_data

                features = self.engineer.transform(batch)
                if features is None:
                    continue

                signal = self.fusion.predict(features, sent_data if use_sentiment else None)
                mtf_ok, _ = self.mtf_gate.allow_signal(batch["ohlcv"], signal.direction)

                if signal.direction != 0 and signal.confidence >= min_conf and mtf_ok:
                    entry, direction = cl, signal.direction
                    sl = entry * (1 - sl_pct) if direction == 1 else entry * (1 + sl_pct)
                    tp = entry * (1 + tp_pct) if direction == 1 else entry * (1 - tp_pct)
                    in_pos = True

        return self._report(trades, initial_balance, balance, df)

    def _report(self, trades: List[Dict], init: float,
                final: float, df: pd.DataFrame) -> Dict:
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
