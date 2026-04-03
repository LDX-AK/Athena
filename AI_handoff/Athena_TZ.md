# ⚡ Athena AI-Bot v2 — Техническое задание

> **Версия:** 1.1 | **Дата:** Апрель 2026 | **Статус:** Актуально (обновлено)

---

## Содержание

1. [Цели и концепция](#1-цели-и-концепция)
2. [Архитектура и компоненты](#2-архитектура-и-компоненты)
3. [Описание модулей](#3-описание-модулей)
4. [API между модулями](#4-api-и-интерфейсы-между-модулями)
5. [Конфигурация и флаги](#5-конфигурация-и-флаги)
6. [Технический стек](#6-технический-стек)
7. [Порядок разработки](#7-порядок-разработки)
8. [Метрики успеха](#8-метрики-успеха)
9. [Риски](#9-риски)
10. [План Следующих Изменений](#10-план-следующих-изменений)

---

## 1. Цели и концепция

### 1.1 Общее описание

Athena AI-Bot v2 — автоматизированная система скальпинг-торговли на рынке криптовалют с элементами искусственного интеллекта. Бот работает одновременно на нескольких биржах (Binance, Bybit, OKX), использует гибридную модель принятия решений на основе **LightGBM + Sentiment**, и опциональный RL-агент (PPO) для динамического управления рисками.

Название — в честь Афины, богини мудрости и стратегии.

### 1.2 Бизнес-цели

- Автоматизация скальпинг-торговли с минимальным участием человека
- Win Rate >50%, Sharpe Ratio >1.5, Max Drawdown <20%
- Максимальный дневной дродаун не более **5% депозита**
- Работа **24/7** без деградации качества сигналов
- Масштабирование с $100 до $100,000+ без переписывания логики

### 1.3 Технические цели

- Latency исполнения ордеров: **<50ms** (WebSocket vs REST ~200ms)
- Одновременное подключение к **3+ биржам** через CCXT
- **~60 признаков** для ML модели (технические + sentiment)
- Hybrid Signal: **LightGBM 70% + Sentiment 30%** с настраиваемыми весами
- Модульная архитектура: каждый компонент заменяется независимо

### 1.4 История проекта

| Версия | Описание | Статус |
|--------|----------|--------|
| v0 (прошлый бот) | Скальпинг без AI, только тех. индикаторы. Низкая прибыльность. | Архивирован |
| v1 (Athena) | LightGBM + CCXT Pro + Docker. Базовая архитектура. | Реализован |
| v2 (текущий) | Hybrid Signal + Sentiment + RL Shield + Streamlit | В разработке |

---

## 2. Архитектура и компоненты

### 2.1 Общая схема потока данных

```
AthenaFetcher (WebSocket)  →  данные OHLCV + стакан
AthenaSentiment (CSV/API)  →  sentiment {score, volume, trend}
AthenaEngineer             →  ~60 признаков для ML
SignalFusion               →  AthenaSignal {direction, confidence}
AthenaRisk.check()         →  AthenaDecision {approved, size_usd}
AthenaShield (PPO)         →  size_multiplier [0, 1]
AthenaRouter.execute()     →  result {status, pnl}
AthenaRisk.update()        →  обновление статистики
AthenaDashboard            →  мониторинг
```

### 2.2 Компоненты системы

| Класс | Файл | Назначение | Зависимости |
|-------|------|-----------|-------------|
| `AthenaFetcher` | `data/fetcher.py` | WebSocket стримы OHLCV + стакан | ccxt.pro |
| `AthenaSentiment` | `data/sentiment.py` | CSV + CryptoPanic sentiment | aiohttp, pandas |
| `AthenaEngineer` | `features/engineer.py` | 60+ признаков (11 блоков) | numpy, pandas |
| `AthenaModel` | `model/signal.py` | LightGBM inference + обучение | lightgbm, sklearn |
| `SignalFusion` | `model/fusion.py` | Hybrid Signal LGBM+Sentiment | AthenaModel |
| `AthenaShield` | `model/rl_shield.py` | PPO Risk Agent (опц.) | stable-baselines3 |
| `AthenaRisk` | `risk/manager.py` | Dynamic Kelly + риск-контроль | — |
| `AthenaRouter` | `execution/router.py` | Исполнение ордеров paper/live | ccxt.pro |
| `AthenaBacktest` | `backtest/runner.py` | Walk-forward бэктест | все выше |
| `AthenaDashboard` | `monitor/streamlit_app.py` | Streamlit визуализация | streamlit |

### 2.3 Режимы запуска

| Команда | Режим | Описание |
|---------|-------|----------|
| `python -m athena --mode train` | Обучение | Загрузка 6 мес. данных, обучение LightGBM |
| `python -m athena --mode train_rl` | Обучение RL | Обучение PPO агента |
| `python -m athena --mode backtest` | Бэктест | Walk-forward тест на истории |
| `python -m athena --mode paper` | Paper trading | Симуляция без реальных денег |
| `python -m athena --mode live` | Live торговля | Реальная торговля |
| `streamlit run monitor/streamlit_app.py` | Дашборд | Визуальный мониторинг :8501 |

---

## 3. Описание модулей

### 3.1 AthenaFetcher — Data Layer

- **Протокол:** WebSocket (CCXT Pro) — latency 5-20ms vs REST 50-200ms
- **Данные:** OHLCV (1m, 15m) + Order Book глубиной 20 уровней
- **Буфер:** `deque` с maxlen=100 свечей на каждую пару/биржу
- **Реконнект:** автоматически при обрыве, пауза 5 сек
- **Historical:** REST API с пагинацией для загрузки данных обучения

### 3.2 AthenaSentiment — Sentiment Layer

**CSV (бэктест — Kaggle):**
- `gautamchettiar/historical-sentiment-data-btc-eth-bnb-ada`
- `pratyushpuri/crypto-market-sentiment-and-price-dataset-2025`
- Автонормализация к `[-1, 1]` независимо от формата исходного CSV
- `merge_asof` — ближайшее значение в прошлом, без look-ahead bias

**CryptoPanic API (live, флаг `SENTIMENT_LIVE_ENABLED=True`):**
- Кэш 15 минут (TTL), timeout 5 сек, fallback score=0
- Бесплатный план: `cryptopanic.com/api/`

### 3.3 AthenaEngineer — Feature Engineering

~60 признаков из 11 блоков:

| Блок | Признаки | Источник | N |
|------|----------|----------|---|
| Ценовые | ret_1..20, price_pos_20/60 | Оригинал | 7 |
| Индикаторы | EMA, RSI, BB, ATR, VWAP, MACD, Stoch | Оригинал | 18 |
| Order Book | ob_imb_5/20, spread, pressure | Оригинал | 5 |
| Order Flow | trade_imbalance, execution_ratio, liquidity | DRW Kaggle 🏆 | 5 |
| Multi-Horizon | ret/vol/range за 5,10,15,30,60,120m | DRW + G-Research 🏆 | 15 |
| Regime Interactions | vol×imbalance, atr×vol | DRW Kaggle 🏆 | 3 |
| Rolling Stats | sharpe/skew/autocorr за 10,30,60 | G-Research 🏆 | 9 |
| Vol Regime | vol_regime, acceleration | PPO State | 4 |
| Volume Dynamics | vol_ratio/zscore/momentum, OBV | DRW Kaggle 🏆 | 9 |
| Временные | hour_sin/cos, sessions, weekend | Оригинал | 8 |
| Sentiment | score, volume, trend, momentum | Kaggle CSV 📊 | 6 |

> 🏆 = из winning solutions Kaggle соревнований (DRW, G-Research)

### 3.4 SignalFusion — Hybrid Signal

Алгоритм:

```
score_lgbm = direction × confidence × LGBM_WEIGHT      # напр. 0.70
score_sent = direction × confidence × SENTIMENT_WEIGHT  # напр. 0.30
total = score_lgbm + score_sent
final_direction  = sign(total)
final_confidence = abs(total) / max_possible
```

При противоречии источников (LGBM=BUY, Sentiment=SELL) — штраф **25%** к confidence.

Настройка:
```python
"LGBM_WEIGHT":        0.70,  # вес LightGBM
"SENTIMENT_WEIGHT":   0.30,  # вес Sentiment (сумма = 1.0)
"SENTIMENT_ENABLED":  False, # отключить sentiment полностью
```

### 3.5 AthenaRisk — Risk Management

**Многоуровневая защита депозита:**

| Проверка | Параметр | Значение по умолч. |
|----------|----------|-------------------|
| Уверенность модели | `min_confidence` | 0.65 |
| Кулдаун после убытка | `cooldown_after_loss_sec` | 300 сек (5 мин) |
| Дневной дродаун | `max_daily_drawdown_pct` | 5% |
| Макс. позиций | `max_open_positions` | 3 |
| Стоп-лосс | `stop_loss_pct` | 0.3% |
| Тейк-профит | `take_profit_pct` | 0.6% (RR 1:2) |

**Dynamic Kelly Criterion:**
```python
f = (p × b - q) / b           # Kelly formula
size = balance × f × 0.25 × confidence  # дробный Kelly (25%)
# p=win_rate, b=avg_win/avg_loss, 0.25=консервативная фракция
```

### 3.6 AthenaShield — PPO RL Agent (опционально)

> ⚠️ `RL_ENABLED=False` по умолчанию. Включать только после стабильного paper trading.

**State Vector (5D):**
```
[0] balance_norm     — текущий баланс / начальный
[1] unrealized_pnl   — нереализованный PnL [-1, +1]
[2] rolling_sharpe   — Sharpe за 24ч / 3 (норм.)
[3] vol_regime       — ATR percentile [0, 1]
[4] sentiment_score  — [-1, +1]
```

**Reward Function:**
```
reward = sharpe_24h × 10 - maxdd_pct × 5 + pnl_today × 0.1
```

---

## 4. API и интерфейсы между модулями

### 4.1 Dataclasses (контракты данных)

```python
@dataclass
class AthenaSignal:
    direction:  int    # 1=BUY | -1=SELL | 0=HOLD
    confidence: float  # [0.0, 1.0]
    symbol:     str    # 'BTC/USDT'
    exchange:   str    # 'binance'
    price:      float
    features:   Dict   # все признаки (для логирования)

@dataclass
class AthenaDecision:
    approved:          bool
    reason:            str
    adjusted_size_usd: float

@dataclass
class ShieldDecision:
    size_multiplier: float  # [0, 1]
    reason:          str
```

### 4.2 Batch формат (Fetcher → Engineer)

```python
batch = {
    "ohlcv":     List[List],  # [[ts, o, h, l, c, v], ...]
    "orderbook": {"bids": [...], "asks": [...], "timestamp": int},
    "symbol":    str,
    "exchange":  str,
    "sentiment": dict,  # опционально
}
```

### 4.3 Sentiment формат

```python
sentiment = {
    "score":  float,  # [-1, +1] нормализованный
    "volume": float,  # log(кол-во упоминаний)
    "trend":  float,  # изменение score за период
}
```

### 4.4 PPO State Vector

```python
AthenaRisk.get_ppo_state() → np.ndarray[float32, shape=(5,)]
# Вызывается из core.py перед каждым решением AthenaShield
```

---

## 5. Конфигурация и флаги

### 5.1 Главные переключатели

```python
"flags": {
    "SENTIMENT_ENABLED":      True,   # sentiment слой вкл/выкл
    "SENTIMENT_LIVE_ENABLED": False,  # CryptoPanic API
    "SENTIMENT_BACKTEST":     True,   # CSV в бэктесте
    "LGBM_WEIGHT":            0.70,   # вес LightGBM
    "SENTIMENT_WEIGHT":       0.30,   # вес Sentiment (сумма=1.0)
    "MTF_FILTER_ENABLED":     True,   # фильтр по 15m тренду
    "RL_ENABLED":             False,  # PPO Shield
    "RL_RETRAIN_EVERY":       100,    # дообучение PPO каждые N сделок
    "STREAMLIT_ENABLED":      True,
    "GRAFANA_ENABLED":        True,
}
```

### 5.2 Риск-параметры

```python
"risk": {
    "max_position_pct":        0.02,   # 2% депозита
    "max_daily_drawdown_pct":  0.05,   # стоп при -5%
    "min_confidence":          0.65,
    "cooldown_after_loss_sec": 300,
    "max_open_positions":      3,
    "stop_loss_pct":           0.003,  # 0.3%
    "take_profit_pct":         0.006,  # 0.6% (RR 1:2)
    "kelly_fraction":          0.25,   # консервативный Kelly
}
```

### 5.3 Переменные окружения (.env)

> ⛔ **КРИТИЧНО:** `.env` добавлен в `.gitignore`. Никогда не коммитить API ключи!

```env
BINANCE_API_KEY=...      BINANCE_SECRET=...
BYBIT_API_KEY=...        BYBIT_SECRET=...
OKX_API_KEY=...          OKX_SECRET=...        OKX_PASSPHRASE=...
CRYPTOPANIC_API_KEY=...
REDIS_URL=redis://localhost:6379
DATABASE_URL=postgresql://athena:secret@localhost:5432/athena
```

---

## 6. Технический стек

| Компонент | Технология | Версия | Назначение |
|-----------|-----------|--------|-----------|
| Язык | Python | 3.10+ | Основной язык |
| Биржи | CCXT Pro | 4.3+ | Unified API + WebSocket |
| ML модель | LightGBM | 4.3+ | Gradient Boosting |
| RL агент | stable-baselines3 | 2.3+ | PPO (опц.) |
| Dashboard | Streamlit | 1.35+ | Мониторинг :8501 |
| Кэш | Redis | 7 | Быстрый кэш |
| БД | TimescaleDB | pg16 | OHLCV история |
| Grafana | Grafana | latest | Метрики и алерты |
| Оркестрация | Docker Compose | 3.9 | Redis + DB + Grafana |
| IDE | VS Code + Copilot Pro | latest | Разработка |

---

## 7. Порядок разработки

| # | Задача | Статус | Критерий готовности |
|---|--------|--------|---------------------|
| 1 | Data Pipeline: WebSocket + CCXT + буферы | ✅ Готово | Данные текут без обрывов |
| 2 | Feature Engineering: 60+ признаков | ✅ Готово | transform() без NaN |
| 3 | LightGBM обучение + Walk-Forward | ✅ Готово | Accuracy >55% |
| 4 | Risk Manager: Kelly + проверки | ✅ Готово | Нет позиций при DD>5% |
| 5 | Execution Router: paper + live | ✅ Готово | Paper PnL корректен |
| 6 | Sentiment: Kaggle CSV + CryptoPanic | ✅ Готово | Загружается без ошибок |
| 7 | Signal Fusion: LGBM 70% + Sent 30% | ✅ Готово | Веса меняются в config |
| 8 | Backtest v2: sentiment + Calmar | ✅ Готово | Sharpe>1.5, DD<20% |
| 9 | Streamlit Dashboard | ✅ Готово | Открывается на :8501 |
| 10 | Paper Trading (2-4 недели) | 🔄 Текущая | WinRate>50%, Sharpe>1.5 |
| 11 | RL Shield PPO обучение | ⏳ Фаза 2 | После стабильного paper |
| 12 | Live Trading ($100-500) | ⏳ Фаза 3 | После 4 нед. paper |
| 13 | Auto-retraining (7-14 дней) | ⏳ Фаза 4 | Cron расписание |
| 14 | VPS деплой близко к бирже | ⏳ Фаза 4 | Latency <15ms |

---

## 8. Метрики успеха

### 8.1 Целевые показатели бэктеста

| Метрика | Минимум | Цель | Описание |
|---------|---------|------|----------|
| Sharpe Ratio | >1.5 | >2.0 | Risk-adjusted доходность |
| Win Rate | >50% | >55% | % прибыльных сделок |
| Max Drawdown | <20% | <10% | Макс. просадка от пика |
| Profit Factor | >1.5 | >2.0 | Профиты / убытки |
| Calmar Ratio | >0.5 | >1.0 | Доход / Max Drawdown |
| Макс. серия SL | <7 | <5 | Подряд убыточных сделок |

### 8.2 Условия перехода к live торговле

- Paper trading **минимум 2-4 недели** с реальными данными
- Win Rate >50%, Sharpe >1.5 за период paper
- Ни разу не сработал daily drawdown лимит 5%
- Весь код понятен, каждая строка объяснима

---

## 9. Риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Переобучение LightGBM | Средняя | Высокое | Walk-forward, ретрейнинг каждые 7-14 дней |
| Смена рыночного режима | Высокая | Среднее | Auto-retraining, мониторинг Sharpe |
| Сбой WebSocket | Средняя | Среднее | Автореконнект с бэкоффом |
| Утечка API ключей | Низкая | Критическое | .gitignore, env vars, только trade-права |
| RL агент деградирует | Средняя | Высокое | RL_ENABLED=False по умолч. |
| Комиссии съедают прибыль | Высокая | Высокое | Учёт 0.04% в бэктесте, limit ордера |

---

## 10. План Следующих Изменений

### 10.1 Runtime и исполнение (утверждено)

- Базовый runtime до paper/live hardening работает на **обычном CCXT (REST polling)**.
- WebSocket/ccxt.pro возвращается только после стабилизации paper-phase и профилирования latency.
- Исполнение в приоритете:
    - `limit` как базовый тип ордера;
    - fallback в `market` только в контролируемых случаях;
    - отдельный трек задач на `post-only` и partial fill handling.

### 10.2 Drift Control и переобучение (утверждено)

- Вводится модуль **AthenaDriftMonitor** для раннего обнаружения деградации модели.
- Источники сигналов drift:
    - rolling win rate,
    - rolling sharpe,
    - profit factor,
    - rolling confidence (опционально).
- Политика retrain:
    - плановый retrain: каждые 7-14 дней,
    - внеплановый retrain: при устойчивом drift-сигнале,
    - cooldown между retrain-задачами.
- Безопасное переключение модели:
    - paper validation gate,
    - rollback на прошлую модель при ухудшении метрик.

### 10.3 Приоритет внедрения

1. Drift monitor + метрики деградации.
2. Trigger policy для retrain (schedule + drift).
3. MTF filter в runtime/backtest.
4. Dashboard writer (`live_stats.json`, `trade_history.json`).
5. Controlled backtest/smoke после каждого крупного блока.

*⚡ Athena AI-Bot v2 | Техническое задание v1.1 | Апрель 2026*
