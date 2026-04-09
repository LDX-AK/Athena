# Athena — протокол полного разделения `v2` и `v3` (RU)

> **Статус:** active / mandatory  
> **Дата фиксации:** 2026-04-09

---

## 1. Цель

Разделить `Athena v2` и `Athena v3` в **две независимые линии разработки**, чтобы:

- не смешивать гипотезы и код;
- не путать артефакты обучения и backtest;
- вести честный regression-поиск по `v2` без загрязнения `v3`-логикой;
- сохранить `v3` как отдельную router-first ветку.

---

## 2. Git / GitHub модель

Используем три постоянные линии:

- `main` — только **общая инфраструктура** и нейтральные fixes;
- `dev/v2-revival` — активная ветка восстановления `Athena v2`;
- `dev/v3-regime-first` — отдельная параллельная ветка `Athena v3`.

### Жёсткие правила
1. **Запрещён прямой merge `v2 -> v3` и `v3 -> v2`.**
2. Общие исправления идут через `main` или через точечный `cherry-pick` после проверки.
3. Любая strategy-specific логика должна оставаться внутри своей ветки.

---

## 3. Разделение артефактов

### Результаты
- `data/results/v2/`
- `data/results/v3/`

### Модели
- `athena/model/v2/`
- `athena/model/v3/`

### Стандартные entrypoints
- `python scripts/run_v2_regression.py ...`
- `python scripts/run_v3_walkforward.py ...`

---

## 4. Что считаем общим

### Можно делить между ветками
- `execution` / `paper-live` plumbing;
- безопасные bugfixes инфраструктуры;
- тестовый каркас и QA automation;
- нейтральные performance / logging fixes.

### Нельзя автоматически переносить между ветками
- router / route-aware logic;
- label/feature tweaks, влияющие на гипотезу стратегии;
- thresholds, filters и execution logic, если они меняют торговое поведение.

---

## 5. Рабочий цикл для `v2-revival`

`v2` теперь ведём как **regression-driven recovery**:

1. воспроизводим последний хороший baseline;
2. находим момент/изменение, где поведение ухудшилось;
3. вносим **одну** новую правку за раз;
4. проверяем:
   - unit tests,
   - regression tests,
   - strict walk-forward;
5. сохраняем артефакты только в `data/results/v2/`;
6. фиксируем выводы в changelog и `ATHENA_V2_REVIVAL_PLAN_RU.md`.

---

## 6. Команды по умолчанию

### `v2`
```bash
python scripts/run_v2_regression.py --candidate core_compact --timeframe 15m --suffix baseline_recheck
```

### `v3`
```bash
python scripts/run_v3_walkforward.py --candidate core_compact --timeframe 15m --suffix router_check
```

---

## 7. Текущее состояние после разделения

- `v3` остаётся отдельной research-веткой;
- активный рабочий фокус проекта переключён на `v2-revival`;
- все новые regression-эксперименты по восстановлению edge идут только через `v2`-контур.
