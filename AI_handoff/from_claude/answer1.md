Мои рекомендации по очереди задач
1. unrealized_pnl — делай ПЕРВЫМ (15 мин)
Это самое простое и даёт реальную пользу для dashboard прямо сейчас. В core.py уже есть "unrealized_pnl": 0.0 — заглушка. Нужно просто подключить:
python# В core.py, в месте где собирается live_stats:
def _calc_unrealized_pnl(router, current_prices: dict) -> float:
    total = 0.0
    for key, pos in router.paper_positions.items():
        symbol = pos["symbol"]
        price  = current_prices.get(symbol, pos["entry"])
        pnl    = (price - pos["entry"]) / pos["entry"] * pos["size_usd"] * pos["direction"]
        pnl   -= pos["commission"]  # вычитаем уже уплаченную комиссию открытия
        total += pnl
    return total
```

Цену берёшь из последней свечи батча — она уже есть в `batch["ohlcv"][-1][4]`. Словарь `current_prices` можно накапливать в цикле по батчам.

---

### 2. Stage 4 v2 — JSONL migration

Copilot и Kimi оба правы в своём анализе. Мой вердикт по вопросам из `consolidated_stage4_for_kimi.md`:

**Q1: Держать JSON array ещё итерацию?** — Да, правильно. Не ломай работающий dashboard без причины.

**Q2: Dual-format reader в Streamlit сейчас или после paper soak?** — После paper soak. Порядок такой:
```
Paper smoke (3-5 дней) → убедились что v1 стабильна
    → добавить JSONL writer параллельно (dual-write)
    → обновить Streamlit для чтения обоих форматов
    → через неделю убрать JSON array writer
Q3: Достаточен ли текущий набор полей? — Почти. Не хватает одного важного поля — model_version (хэш или timestamp обучения модели). Это критично для корреляции дрифта с версией модели.
Q4: Edge cases в atomic write + bounded history под высоким rate? — Вижу одну потенциальную проблему:
python# В _sync_flush текущая логика:
history = self._read_history()    # читаем файл
history.extend(self._trade_buffer) # добавляем буфер
# ...пишем обратно

# Проблема: если flush_interval=5s и за 5s пришло 50 закрытий
# (маловероятно для скальпинга, но возможно при SL sweep)
# — всё нормально, буфер батчится. Это ОК.

# Реальная проблема: _read_history() читает ВЕСЬ файл (до 1000 записей)
# при каждом flush. При max_history=1000 и flush каждые 5с
# это 1000 JSON объектов каждые 5 секунд — приемлемо.
# Проблема только если max_history растёт. Держи его в 500-1000.
Это не блокер, но для v2 JSONL решает именно эту проблему — append-only без чтения всего файла.

3. Paper smoke window — чек-лист
Когда запустишь paper mode, проверь именно это:
bash# 1. Файлы создаются
ls -la data/live_stats.json data/trade_history.json

# 2. live_stats обновляется (смотри timestamp)
watch -n 6 'python -c "import json; d=json.load(open(\"data/live_stats.json\")); print(d[\"timestamp\"], d[\"balance\"])"'

# 3. После первого SL/TP — trade_history не пустой
python -c "import json; h=json.load(open('data/trade_history.json')); print(len(h), h[-1] if h else 'empty')"

# 4. Streamlit отображает equity curve
streamlit run athena/monitor/streamlit_app.py
```

---

## ⚠️ Одна вещь которую стоит починить до smoke

В `core.py` есть потенциальный race condition — `writer.update_live_stats(live_stats)` вызывается в начале итерации цикла, **до** того как обработан новый батч. Это значит что первые несколько итераций stats будут с данными от предыдущего батча. Это не критично, но лучше перенести вызов `update_live_stats` в конец итерации, после обработки сигнала.

---

## 🗺️ Итоговая очередь
```
1. unrealized_pnl (15 мин) → сразу
2. Paper smoke 3-5 дней → параллельно с разработкой
3. Stage 4 v2 (JSONL) → после smoke
4. model_version поле в telemetry → вместе с v2
5. update_live_stats в конец итерации → мелкий фикс, можно сейчас
Передавай Kimi когда вернётся — пусть подтвердит или добавит. 🏛️Я передам твои советы GithubСopilot Pro,  он запишет в change_history чтоб другие потом увидели..02:21Отличная схема координации! 👍
Одно уточнение для Copilot когда будет записывать в change_history.md — предложи ему использовать такой формат записи, чтобы было понятно что это рекомендации на будущее, а не уже реализованное:
markdown### [2026-04-02] Claude review — pending recommendations

Source: Claude (this session)
Status: Pending implementation / review by Kimi

#### Recommended priority queue:
1. `unrealized_pnl` — wire real calculation from paper_positions (~15 min)
2. Paper smoke window — validate telemetry before Stage 4 v2
3. Stage 4 v2 (JSONL migration) — after smoke confirms v1 stable
4. Add `model_version` field to telemetry (correlate drift with model)
5. Move `update_live_stats()` call to end of iteration in core.py (minor race)

#### Edge case noted:
- `_sync_flush` reads entire history file on every flush (read-modify-write).
  Acceptable at max_history=1000, becomes bottleneck if limit grows.
  JSONL in v2 solves this by design.

#### Stage 4 v2 migration path (recommended):
- Dual-write JSON + JSONL in parallel first
- Update Streamlit to support both formats
- Remove JSON array writer after 1 week stable
- Do NOT migrate before paper smoke confirms v1 stable

#### Field gap:
- Add `model_version` (hash or train timestamp) to live_stats
  for drift/model correlation in dashboard
Это даст Kimi и тебе чёткий контекст когда вернётся. Удачи с smoke window! 🏛️⚡