# Архив стратегии Athena v2 (RU)

> **Статус:** законсервировано как baseline / негативный контроль  
> **Дата фиксации:** 2026-04-08  
> **Ветка:** `Athena v2 short-only / meta-filter salvage`

---

## 1. Зачем архивировать эту ветку

Эта стратегия прошла длинный цикл честных проверок:

- MTF / macro / hierarchy эксперименты
- adaptive-mode
- label redesign (`atr_hilo` и др.)
- feature ablation (`core_compact`, `price_action_core`, `atr_hilo_core`)
- raw signal diagnostics
- `short-only` retrain
- `meta-filter` по часам / режимам / confidence

По итогам выяснилось:

> **ядро short-side не нулевое, но недостаточно сильное для устойчивой торговли в рамках текущей архитектуры v2**.

Это не мусор и не провал — это **важный контрольный baseline**, от которого надо отталкиваться при разработке `Athena v3`.

---

## 2. Что именно зафиксировано в архиве

Физическая копия артефактов сохранена в:

```text
backups/strategy_archive_2026-04-08/
```

### Содержимое архива
- `athena_brain_15m_core_compact_2026-04-08.pkl`
- `athena_brain_15m_core_compact_feature_importance.json`
- `walkforward_15m_core_compact_q4_dedicated_short_only.json`
- `walkforward_15m_core_compact_q4_dedicated_short_normal.json`
- `signal_diagnostics_core_compact_short_only_q4.json`

---

## 3. Краткая эволюция ветки

### Этап 1 — Универсальная hybrid-модель
- `LightGBM + Sentiment`
- общая directional логика для mixed regime market
- результат: нестабильный и отрицательный honest OOS

### Этап 2 — Фильтры и защита
- `MTF gate`
- `macro filter`
- `adaptive mode`
- результат: локальные улучшения без устойчивого прохода по строгому holdout

### Этап 3 — Пересборка labels/features
- `atr_hilo`, `atr_first_touch`, `atr_intrabar`
- compact/ablation сценарии
- результат: `core_compact` стал «наименее плохим», но всё ещё отрицательным

### Этап 4 — Диагностика raw edge
- side/regime/hour confidence breakdown
- результат:
  - `long` — явный drag
  - `short` — слабый положительный raw edge
  - `high-confidence` не означал «лучше»

### Этап 5 — Dedicated short-only salvage
- one-sided `label_target=short`
- scoped gating + meta-filter
- результат:
  - сырой edge стал чуть лучше,
  - но net performance на честном Q4 остался отрицательным

---

## 4. Проверенные результаты

### 4.1 Dedicated short-only Q4 holdout

| Профиль | Сделок | Доходность | Sharpe | PF |
|---|---:|---:|---:|---:|
| Conservative | `263` | `-0.1927%` | `-3.26` | `0.66` |
| Aggressive | `230` | `-0.4136%` | `-1.48` | `0.82` |

Источник:
- `data/results/walkforward_15m_core_compact_q4_dedicated_short_only.json`

### 4.2 Dedicated short-only + normal regime Q4 holdout

| Профиль | Сделок | Доходность | Sharpe | PF |
|---|---:|---:|---:|---:|
| Conservative | `143` | `-0.1418%` | `-4.53` | `0.57` |
| Aggressive | `121` | `-0.3141%` | `-2.18` | `0.75` |

Источник:
- `data/results/walkforward_15m_core_compact_q4_dedicated_short_normal.json`

### 4.3 Диагностика short-only модели

Источник:
- `data/results/signal_diagnostics_core_compact_short_only_q4.json`

Ключевые выводы:
- `Signals = 4545`
- `edge_per_signal = +0.00016077`
- `win_rate ≈ 49.53%`
- сырой short-edge **чуть положительный**, но слишком слабый для текущей схемы исполнения

---

## 5. Что из ветки v2 нельзя выбрасывать

Даже при pivot в `v3` из этой ветки сохраняется много полезного:

- strict walk-forward harness
- raw diagnostics по confidence / side / regime / hour
- meta-filter infrastructure
- one-sided training (`label_target`)
- observability и telemetry
- dashboard / Mermaid / history pipeline

То есть архивируется **не инфраструктура**, а именно **старая strategy hypothesis**.

---

## 6. Как использовать этот архив дальше

Использовать как:

1. **контрольную точку** для сравнения новых веток;
2. **негативный контроль**, чтобы не возвращаться к уже проверенным тупиковым вариантам;
3. источник повторно используемых инструментов и инфраструктуры.

### Важное правило

Если новая ветка `v3` не может уверенно побить этот baseline на честном OOS,
значит она ещё не готова для развития вглубь.

---

## 7. Решение по ветке

**Вердикт:**

> `Athena v2 short-only / meta-filter salvage` закрывается как исследованный baseline и не рассматривается как production-ready стратегия.

Дальше основная разработка идёт в сторону:

- `Regime-first`
- `Session-aware`
- `rolling retrain`
- `router-based strategy selection`
