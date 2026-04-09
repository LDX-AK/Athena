# Athena v3 — Regime-first + Session-aware  
## Живой план внедрения и ТЗ (RU)

> **Статус:** draft / living document / separate parallel track  
> **Дата старта:** 2026-04-08  
> **Режим обновления:** пополняется после каждого крупного шага и каждой ветки экспериментов
>
> **Важно:** с `2026-04-09` `Athena v3` ведётся только как отдельная параллельная ветка `dev/v3-regime-first`. Активный рабочий фокус проекта перенесён на `Athena v2 Revival`, а прямое смешивание `v2` и `v3` логики запрещено.

---

## 1. Контекст и причина перехода

`Athena v2` прошла честный исследовательский цикл:

- `hierarchy / macro / adaptive`
- `label redesign`
- `short-only`
- `meta-filter`
- `strict Q4 walk-forward`

Главный вывод:

> **одна общая модель на смешанных рыночных режимах и торговых часах не даёт устойчивого edge.**

При этом инфраструктура проекта стала сильной:

- unit/regression tests
- walk-forward harness
- signal diagnostics
- observability / dashboard
- backtest/runtime gating

Значит проблема смещается с “сломанных инструментов” на **архитектуру торговой гипотезы**.

---

## 2. Новая базовая гипотеза v3

### 2.1 Основная идея

Рынок надо рассматривать не как единый поток, а как комбинацию:

1. **режима волатильности / поведения**
   - `quiet`
   - `normal`
   - `hot`

2. **временного / сессионного контекста**
   - `asia`
   - `europe`
   - `us`
   - `eu_us_overlap`
   - `weekend`

3. **локальной торговой логики**, подходящей именно под эту комбинацию.

Иначе говоря:

> сначала **router**, потом **strategy**, потом **execution**.

### 2.2 Что это меняет

Вместо одной модели “на всё” Athena v3 должна решать так:

- определить `regime`
- определить `session`
- выбрать подстратегию:
  - `no_trade`
  - `mean_reversion`
  - `directional`
  - `breakout`

### 2.3 Бонусные идеи, которые сразу включаем в v3

Ниже — не «когда-нибудь потом», а **сразу включённые элементы архитектуры v3**:

#### ✅ Берём сразу
1. **`Session × Regime confidence penalties`**
   - confidence калибруется не глобально, а с поправкой на комбинацию `session x regime`;
   - это дешёвый и очень полезный first-order слой.

2. **`Two-level router`**
   - уровень 1: `regime -> allowed routes`;
   - уровень 2: `session -> preferred route / confidence multiplier`;
   - это считается **ядром Athena v3**, а не дополнительной опцией.

3. **`Эвристики quiet/hot`**
   - для `quiet` и `hot` сразу допускаются простые rule-based прототипы;
   - это хороший первый шаг перед более сложным ML внутри маршрута.

4. **`Router diagnostics dashboard`**
   - route counts, `last_route_reason`, session/regime route breakdown;
   - ведём параллельно с разработкой, чтобы не получить «чёрный ящик».

#### 🟡 Берём позже / частично
5. **`Session-adaptive SL/TP`**
   - полезно, но это не first-order fix;
   - переносится на вторую волну после проверки router-first архитектуры.

6. **`Regime-adaptive threshold`**
   - берём **частично**;
   - не как отдельную сложную ветку, а как часть общего confidence calibration слоя.

---

## 3. Ограничения и правила разработки

### 3.1 Принципы
- каждая ветка начинается с **TDD**;
- после каждого этапа обязательны:
  - unit tests,
  - regression tests,
  - strict walk-forward;
- если ветка не проходит honest OOS, она **архивируется**, а не допиливается бесконечно;
- все временные признаки внутри кода храним в **UTC**, а человекочитаемые сессии описываем отдельно.

### 3.2 Что НЕ делаем сразу
- не включаем RL как основу новой логики;
- не запускаем live-trading до подтверждённого paper/holdout результата;
- не строим сразу сверхсложную смесь из 10 стратегий.

---

## 4. Пользовательская идея про торговые сессии — как встраиваем

Пользовательская гипотеза верная: особенности рынка зависят не только от волатильности, но и от **времени суток / активной сессии**.

### Предварительная разметка v1 (для кода — в UTC)

| Bucket | UTC | Смысл |
|---|---|---|
| `asia` | `00:00–08:00` | Азия / Тихоокеанский поток, часто умеренная активность |
| `europe` | `07:00–15:00` | Европа / Лондон, утренние импульсы и рост ликвидности |
| `us` | `13:00–22:00` | США, новости и высокая волатильность |
| `eu_us_overlap` | `13:00–15:00` | пиковое перекрытие Европа + США |
| `weekend` | Sat/Sun | отдельный крипто-режим с иной ликвидностью |

> Важно: для крипты это не буквальные «биржевые открытия», а прокси ликвидности, потока участников и волатильности.

---

## 5. Цели v3

### 5.1 Функциональные цели
1. Ввести `SessionContext` в feature layer.
2. Построить `RegimeRouter`, который выбирает подстратегию.
3. Запустить несколько простых prototype-веток:
   - `quiet_mean_reversion_v1`
   - `normal_directional_v1`
   - `hot_breakout_v1`
4. Перейти на короткий rolling retrain:
   - train: `30–45 дней`
   - validation: `7 дней`
   - holdout/test: `7 дней`
5. Для каждой ветки получать не только PnL, но и diagnostics по side / regime / session / hour.

### 5.2 Нефункциональные цели
- без look-ahead bias;
- единое хранение артефактов в `data/results/`;
- обязательные changelog updates в процессе;
- все ветки должны быть повторяемыми командами из терминала.

---

## 6. Древовидная структура развития (предварительная)

```text
Athena v3
├── A. Regime Router Core
│   ├── A1. SessionContext features
│   ├── A2. RegimeRouter v1 (rule-based)
│   └── A3. Router diagnostics + route_history
│
├── B. Strategy Modules
│   ├── B1. quiet_mean_reversion_v1
│   ├── B2. normal_directional_v1
│   ├── B3. hot_breakout_v1
│   └── B4. no_trade fallback
│
├── C. Training / Validation Layer
│   ├── C1. Rolling walk-forward harness
│   ├── C2. Weekly retrain policy
│   ├── C3. Drift-triggered early retrain
│   └── C4. Session/regime diagnostics
│
└── D. Branch Decisions
    ├── if breakout works -> deepen breakout path
    ├── if mean reversion works -> deepen MR path
    ├── if router helps but modules weak -> redesign features/labels
    └── if all fail -> pivot to a new family of strategies
```

---

## 7. Поэтапный план внедрения

## Этап 0 — Freeze / archive baseline

### Цель
Зафиксировать предыдущую ветку так, чтобы новые эксперименты было с чем сравнивать.

### Deliverables
- архив артефактов `v2`;
- обновлённые `change_history.md` и `change_history_ru.md`;
- архивный документ по ветке `v2`.

### Acceptance gate
- все файлы присутствуют;
- baseline больше не считается production-кандидатом.

**Статус:** ✅ выполнено

---

## Этап 1 — SessionContext v1

### Цель
Добавить в `AthenaEngineer` явные признаки, связанные со временем рынка.

### Что добавить
- `session_asia`, `session_europe`, `session_us`, `session_overlap`
- `is_weekend`
- `hour_bucket`
- возможно `session_open_phase` / `session_close_phase`

### Тесты
- unit test на корректную классификацию UTC-часов;
- feature-pipeline test, что новые поля присутствуют и не ломают transform();
- regression: старые тесты не падают.

### Решение после этапа
- если session features статистически различают edge → идём дальше;
- если нет → оставляем как вспомогательные признаки и делаем упор на regime-only.

**Текущий статус:** ✅ базовый `SessionContext v1` уже внедрён в `AthenaEngineer` и покрыт unit tests; следующий gate — diagnostics / strict WF.

---

## Этап 2 — RegimeRouter v1 (rule-based)

### Цель
Сделать простой роутер без сложного ML, чтобы проверить саму архитектуру.

### Базовые правила v1
- `quiet` → `no_trade` или `mean_reversion`
- `normal` → `directional`
- `hot` → `breakout` или `no_trade`

### Обязательная архитектура router v1
- router делаем **двухуровневым**:
  1. `regime` определяет, какие маршруты вообще разрешены;
  2. `session` определяет приоритет, confidence penalty / boost и допустимость входа.
- confidence после сигнала калибруется через `session x regime` слой, а не одним порогом на все случаи.
- `quiet/hot` допускают специальные эвристические ветки уже в первой реализации.

### Что вернуть из роутера
```python
{
  "route": "normal_directional",
  "regime": "normal",
  "session": "europe",
  "reason": "vol_regime=0.43 + europe session"
}
```

### Тесты
- unit tests для выбора маршрута;
- tests для block/pass поведения в backtest;
- telemetry tests для `route_history` / `last_route_reason`.

### Acceptance gate
- роутер объясним;
- не ломает pipeline;
- можно честно увидеть, какие маршруты вообще активируются.

**Текущий статус:** ✅ минимальный `RegimeRouter v1` уже добавлен в код как rule-based scaffold с `session x regime` confidence calibration и route diagnostics в backtest-отчёт; следующий gate — strict WF и dashboard/runtime расширение.

---

## Этап 3 — Быстрые подстратегии-прототипы

### 3A. `quiet_mean_reversion_v1`
**Гипотеза:** в спокойном режиме лучше работает возврат к среднему.

Кандидаты признаков:
- `vwap_dist`
- `bb_pos`, `bb_width`
- `rsi`, `rsi_slope`
- `ema_9_dist`, `ema_50_dist`

**Kill criteria:** если на validation нет жизни, ветка архивируется без углубления.

### 3B. `normal_directional_v1`
**Гипотеза:** в balanced / normal режиме работает селективный directional подход.

Кандидаты признаков:
- `ret_*`
- `vol_*`
- `ema_cross_9_21`
- `trade_imbalance`
- `atr_norm`

### 3C. `hot_breakout_v1`
**Гипотеза:** в горячем режиме лучше не mean reversion, а continuation / breakout.

Кандидаты признаков:
- `range_*`
- `vol_acceleration`
- `bb_width`
- `atr_ratio`
- `high_*_dist`, `low_*_dist`

### Тесты на этапе 3
- unit tests для логики входа/отбраковки;
- synthetic backtest cases;
- быстрый strict walk-forward на June + Q4.

**Текущий статус:** ✅ первый живой прототип `quiet_mean_reversion_v1` уже внедрён в `athena/strategy/prototypes.py` и подключён к router/backtest. Честная June validation пока всё ещё отрицательная (`-0.028%`, Sharpe `-3.23`, PF `0.66` в conservative), поэтому ветку пока рассматриваем как рабочий черновик, а не как подтверждённую edge-модель.

---

## Этап 4 — Rolling retrain harness v1

### Цель
Уйти от больших и редких общих обучений к короткому циклу.

### Схема v1
- `train = 30–45 дней`
- `validation = 7 дней`
- `test = следующие 7 дней`
- обновление = раз в неделю

### Что требуется
- новый runner для sliding windows;
- сравнение стратегий по одинаковым окнам;
- возможность retrain по drift-сигналу.

### Acceptance gate
- reproducible commands;
- результаты сохраняются в JSON;
- можно строить сводную матрицу за квартал.

---

## Этап 5 — Диагностика по session × regime

### Цель
Понять, где именно находится edge.

### Срезы, которые обязательно считаем
- `session_breakdown`
- `regime_breakdown`
- `session x regime`
- `hour_breakdown`
- `weekday vs weekend`
- `route_breakdown`
- `route x regime`
- `route x session`
- `last_route_reason` / `route_history`

### Решения по итогам
- если edge живёт только в `normal + europe/us` → усиливаем именно эту ветку;
- если `hot` работает лучше → двигаемся в breakout-first;
- если `quiet` работает лучше → делаем mean-reversion-first.

---

## Этап 6 — Дерево решений после первых тестов

```text
Если RegimeRouter + SessionContext улучшает validation и Q4 holdout:
    ├── выбрать лучшую ветку (MR / directional / breakout)
    ├── усилить её ML-моделью внутри маршрута
    └── подключить rolling retrain + drift retrain

Если validation хорошая, но holdout слабый:
    ├── считать ветку хрупкой
    ├── упростить логику и уменьшить degrees of freedom
    └── повторить на новых окнах

Если все 3 подстратегии проваливаются:
    ├── заархивировать `v3a` как ещё один контроль
    └── переходить к новой семье идей (например orderflow-heavy / event-driven)
```

---

## 8. Обязательные промежуточные проверки

| Этап | Проверка | Команда / артефакт | Критерий |
|---|---|---|---|
| 1 | unit tests | `python -m unittest tests.test_feature_pipeline ...` | новые session features корректны |
| 2 | router tests | `python -m unittest tests.test_*router*` | route selection объяснима |
| 3 | branch sanity | быстрый backtest / synthetic tests | ветка хотя бы логически жива |
| 4 | strict WF | runner JSON в `data/results/` | честный OOS не хуже baseline |
| 5 | diagnostics | `signal_diagnostics_*.json` | понятное место edge / anti-edge |
| 6 | regression | `python -m unittest discover -s tests` | полная регрессия не сломана |

---

## 9. ТЗ на ближайший цикл внедрения

### 9.1 Обязательные deliverables
1. `SessionContext` в feature layer.
2. `RegimeRouter` как отдельный модуль/слой.
3. Минимум три route-aware prototype стратегии.
4. Short rolling walk-forward harness.
5. Новые diagnostics по `session x regime`.
6. Документирование всех веток в changelog и этом файле.

### 9.2 Критерии приёмки
Новая ветка считается перспективной, если:
- проходит все unit/regression tests;
- даёт адекватную и объяснимую route telemetry;
- на honest holdout не уступает архивному baseline;
- при этом остаётся интерпретируемой, а не “подогнанной”.

### 9.3 Критерии остановки ветки
Ветка закрывается, если:
- validation и holdout противоречат друг другу без понятной причины;
- improvement держится только на микровыборке;
- никакой session/regime slice не показывает устойчивого преимущества.

---

## 10. Какие документы поддерживать по ходу работы

Обновлять после каждого значимого шага:

- `change_history.md`
- `change_history_ru.md`
- `Athena_TZ.md`
- `docs/ATHENA_V2_STRATEGY_ARCHIVE_RU.md`
- `docs/ATHENA_V3_REGIME_FIRST_PLAN_AND_TZ_RU.md`

Дополнительно сохранять результаты в:

- `data/results/`
- `backups/strategy_archive_*`

---

## 11. История изменений этого документа

### [2026-04-08] Initial draft created
- зафиксирован pivot с `v2 salvage` на `v3 regime-first`;
- описана древовидная программа развития;
- добавлены промежуточные тестовые этапы и stop/go gates;
- включён session-aware слой как часть новой гипотезы.

### [2026-04-08] Bonus ideas promoted into the core plan
- `Session x Regime confidence penalties` переведены в обязательный cheap-win слой;
- `Two-level router` зафиксирован как ядро `v3`;
- `quiet/hot` эвристики включены как ранние prototype-ветки;
- router diagnostics добавлены как обязательная часть честной разработки;
- `session-adaptive SL/TP` и часть adaptive thresholds оставлены на вторую волну.

### [2026-04-09] Version split formalized
- `v3` официально переведена в отдельную Git/GitHub ветку `dev/v3-regime-first`;
- `v2` расконсервирована как независимый track `dev/v2-revival`;
- protocol разделения зафиксирован в `docs/ATHENA_BRANCH_SEPARATION_PROTOCOL_RU.md`;
- все новые `v3` артефакты должны сохраняться отдельно от `v2`.

---

## 12. Короткий practical summary

Если совсем по делу:

> `v2` мы не удаляем, а замораживаем как baseline.  
> `v3` строим как router-first систему:  
> **regime + session → choice of strategy → rolling retrain → strict WF check**.

И только если какая-то ветка выдерживает честный holdout,
она получает право на дальнейшее усложнение.
