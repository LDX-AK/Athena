# История изменений Athena (RU)

## Правила
- Этот файл фиксирует крупные и содержательные изменения проекта.
- После каждого большого этапа сюда добавляется запись с датой, кратким итогом и проверкой.
- Записи держим короткими, фактологичными и опирающимися на тесты/результаты.

## Текущий статус
- Ветка `Athena v2 short-only / meta-filter salvage` **законсервирована как baseline**.
- Архив артефактов сохранён в `backups/strategy_archive_2026-04-08/`.
- Активный фокус проекта переведён на `Athena v3: Regime-first + Session-aware + rolling retrain`.

## Рабочий список на следующую фазу
1. Внедрить `SessionContext` на основе UTC-часов, overlap и weekend-флагов.
2. Построить `RegimeRouter` (`quiet / normal / hot` + `asia / europe / us / overlap`).
3. Проверить rule-based подстратегии как быстрые прототипы:
   - `quiet_mean_reversion`
   - `normal_directional`
   - `hot_breakout`
4. Перевести retrain на короткие rolling-окна и честный step-by-step walk-forward.

## Крупные завершённые этапы

### [2026-04-01] Синхронизация и восстановление окружения
- Репозиторий синхронизирован с GitHub `main`.
- Восстановлена рабочая `.venv` и базовая среда запуска.
- Зафиксированы проблемы совместимости отдельных зависимостей на машине, после чего собран стабильный baseline.

### [2026-04-01] Runtime hardening: paper lifecycle, risk sync, smoke QA
- Runtime переведён на обычный `ccxt` для фазы стабилизации.
- Исправлен жизненный цикл paper-сделок: открытие → контроль → закрытие → учёт PnL.
- Добавлены smoke/import проверки и базовые тесты для конфигурации и feature pipeline.

### [2026-04-01 — 2026-04-02] Drift / retrain / MTF / telemetry
- Добавлены `AthenaDriftMonitor` и политика retrain-trigger.
- Подключён MTF gate в runtime и backtest.
- Введён writer телеметрии и runtime-статистики (`live_stats.json`, `trade_history.json`).
- Система наблюдаемости стала пригодной для paper-режима и расследования деградации.

### [2026-04-03 — 2026-04-08] Исследовательский цикл strict 15m walk-forward
- Прогнаны `hierarchy`, `macro-filter`, `adaptive-mode` и связанные вариации.
- Честный OOS по этим веткам остался отрицательным; они сохранены как отрицательный контроль.
- Добавлены новые label-моды: `atr_hilo`, `atr_first_touch`, `atr_intrabar`.
- Добавлены компактные сценарии: `core_compact`, `price_action_core`, `atr_hilo_core`.

### [2026-04-08] Усиление наблюдаемости и диагностики сигналов
- В Streamlit и runtime добавлены счётчики блокировок, причины, истории фильтров и диаграммы.
- Созданы Mermaid-схемы архитектуры и runtime-потока.
- Добавлен диагностический слой по raw edge:
  - confidence buckets,
  - side breakdown,
  - regime breakdown,
  - hour breakdown.
- Ключевой вывод: `long` тянул систему вниз, `short` сохранял лишь слабый положительный raw edge.

### [2026-04-08] Scoped filters, dedicated short-only retrain, meta-filter
- Добавлены флаги `--direction`, `--regime`, `--meta-hours`, `--meta-regimes`, `--meta-min-confidence`, `--meta-max-confidence`.
- В обучение добавлен `label_target=short|long|both`.
- Исправлено соответствие `classes_ -> direction` для бинарных моделей.
- Свежая проверка:
  - `python -m unittest discover -s tests` → `Ran 62 tests in 0.806s, OK`.
- Q4 dedicated `short-only` остался в минусе:
  - conservative `-0.1927%`, Sharpe `-3.26`, PF `0.66`
  - aggressive `-0.4136%`, Sharpe `-1.48`, PF `0.82`
- Meta-filter дал красивые локальные validation-метрики, но не спас честный holdout.

### [2026-04-08] Решение о повороте архитектуры
- Ветка `Athena v2 short-only / meta-filter salvage` заморожена как архивный baseline.
- Основное развитие перенесено в `Athena v3` с фокусом на:
  - `Regime-first`
  - `Session-aware`
  - короткие rolling-окна retrain
  - древовидную программу экспериментов вместо одной линейной гипотезы.

### [2026-04-08] Старт Athena v3 implementation: Stage 1 + Stage 2 scaffold
- В план напрямую включены сильные bonus-идеи:
  - `Session x Regime confidence penalties`
  - `Two-level router`
  - `quiet/hot` heuristics
  - `router diagnostics`
- В `AthenaEngineer` добавлены явные `SessionContext` поля:
  - `session_asia`, `session_europe`, `session_us`, `session_overlap`, `is_weekend`, `hour_bucket`
- Добавлен rule-based `RegimeRouter v1` с `session x regime` confidence calibration.
- В backtest добавлены route diagnostics:
  - `route_counts`
  - `last_route_reason`
  - `route_history`
- Свежая полная проверка:
  - `.venv/bin/python -m unittest discover -s tests` → `Ran 70 tests in 1.016s, OK`

### [2026-04-08] Первый route-aware прототип: `quiet_mean_reversion_v1`
- Добавлен новый модуль `athena/strategy/prototypes.py` и пакет `athena/strategy/`.
- Реализован первый живой rule-based прототип для `quiet -> mean_reversion`:
  - oversold quiet setup → `long`
  - overbought quiet setup → `short`
  - neutral quiet setup → `flat`
- Прототип подключён прямо в `athena/backtest/runner.py` через `RoutePrototypeEngine` и пишет причину в `last_route_reason` / `router_history`.
- Добавлены unit tests в `tests/test_strategy_prototypes.py`.
- Свежая проверка:
  - `.venv/bin/python -m unittest discover -s tests` → `Ran 75 tests in 0.951s, OK`
- Честная initial validation (June) пока отрицательная, но модуль реально активен:
  - conservative `38` trades, `-0.0279%`, Sharpe `-3.23`, PF `0.66`
  - aggressive `23` trades, `-0.1212%`, Sharpe `-4.72`, PF `0.53`

### [2026-04-09] Полное разделение `v2` и `v3`
- Официально введён protocol разделения в `docs/ATHENA_BRANCH_SEPARATION_PROTOCOL_RU.md`.
- `Athena v2` расконсервирована как активная независимая ветка `dev/v2-revival`.
- `Athena v3` закреплена как отдельная параллельная ветка `dev/v3-regime-first`.
- Добавлены helpers для чистого разделения артефактов:
  - `athena/track_paths.py`
  - `scripts/run_v2_regression.py`
  - `scripts/run_v3_walkforward.py`
- Результаты и модели теперь должны храниться отдельно:
  - `data/results/v2/`, `data/results/v3/`
  - `athena/model/v2/`, `athena/model/v3/`
- Активный рабочий фокус команды переключён на `v2-revival` и regression-driven правки.
- Проверка:
  - `.venv/bin/python -m unittest tests.test_track_paths tests.test_15m_scripts` → `Ran 17 tests in 0.623s, OK`

---

> Поддерживаемые документы для следующей фазы:
> - `change_history.md`
> - `change_history_ru.md`
> - `Athena_TZ.md`
> - `docs/ATHENA_V2_STRATEGY_ARCHIVE_RU.md`
> - `docs/ATHENA_V3_REGIME_FIRST_PLAN_AND_TZ_RU.md`
