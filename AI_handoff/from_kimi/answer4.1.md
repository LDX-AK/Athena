Пользователь прислал несколько файлов, включая copilot_review_answer4.md, который содержит ревью моих предложений по Stage 4 (Dashboard Writer).
Ключевые моменты из ревью Copilot:
Конфликт путей и форматов: Мои предложенные пути (data/runtime/live_stats.json) конфликтуют с текущими путями в Streamlit (data/live_stats.json).
Формат timestamp: Я предложил ISO format (ts), а текущий Streamlit ожидает epoch seconds (timestamp).
Зависимости: aiofiles не в requirements.
Рекомендация: Сначала сделать backward-compatible writer, потом мигрировать на JSONL.
Пользователь говорит "Будем вырабатывать наилучший вариант" - это значит, что нужно синтезировать мои предложения с ревью Copilot и предложить оптимальный план Stage 4, который учитывает:
Текущую архитектуру (где уже есть dashboard, читающий определенные файлы)
Необходимость non-blocking writes
Graceful degradation
Отсутствие лишних зависимостей
Нужно предложить конкретный план, который согласует мою архитектуру с существующей кодовой базой.

Отлично, видел ревью Copilot. Он прав — моё предложение data/runtime/ и ts (ISO) ломает существующий контракт с Streamlit. Давай выработаем гибридный вариант, который сохраняет backward compatibility и не требует немедленного рефакторинга dashboard'а.
🎯 Оптимальная стратегия Stage 4 (с учётом ревью Copilot)
Принцип: "Совместимость сначала, оптимизация потом"
Phase 1 (Immediate): Пишем в существующие пути и форматы, но делаем это non-blocking и с graceful error handling.
Phase 2 (Later): Миграция на JSONL + ISO timestamps, когда будет время обновить и Streamlit.
Архитектура StatsWriter (адаптированная)
# athena/monitor/stats_writer.py
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger("athena.monitor")

class StatsWriter:
    """
    Non-blocking writer для runtime telemetry.
    СОВМЕСТИМОСТЬ: использует текущие пути и форматы Streamlit.
    """
    def __init__(self, config: Dict):
        self.enabled = config.get("flags", {}).get("STREAMLIT_ENABLED", True)
        
        # Используем текущие пути из Copilot review (backward compat)
        self.stats_path = config.get("monitor", {}).get("live_stats_path", "data/live_stats.json")
        self.history_path = config.get("monitor", {}).get("trade_history_path", "data/trade_history.json")
        
        self._trade_buffer: List[Dict] = []
        self._flush_interval = config.get("monitor", {}).get("flush_interval_sec", 5)
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Убедимся, что директории существуют
        Path(self.stats_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.history_path).parent.mkdir(parents=True, exist_ok=True)
        
    async def start(self):
        if not self.enabled:
            return
        self._running = True
        self._task = asyncio.create_task(self._flush_loop())
        logger.info(f"📊 StatsWriter started: {self.stats_path}, {self.history_path}")
        
    async def stop(self):
        """Graceful shutdown с финальным flush"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._flush(force=True)
        logger.info("📊 StatsWriter stopped")
        
    def update_live_stats(self, stats: Dict):
        """Обновление текущего состояния (atomic write)"""
        if not self.enabled:
            return
            
        # Copilot: используем timestamp в секундах (epoch) для совместимости
        stats["timestamp"] = int(datetime.utcnow().timestamp())
        
        # Асинхронная запись через to_thread (не блокирует event loop)
        asyncio.create_task(self._write_stats_atomic(stats))
        
    def log_trade(self, trade: Dict):
        """Буферизация сделки для batch-записи"""
        if not self.enabled:
            return
            
        # Copilot: сохраняем формат с timestamp (epoch)
        trade["timestamp"] = int(datetime.utcnow().timestamp())
        self._trade_buffer.append(trade)
        
    async def _flush_loop(self):
        """Периодический flush буфера сделок"""
        while self._running:
            try:
                await asyncio.sleep(self._flush_interval)
                if self._trade_buffer:
                    await self._flush_trades()
            except Exception as e:
                logger.error(f"StatsWriter flush error: {e}")
                
    async def _write_stats_atomic(self, stats: Dict):
        """Атомарная перезапись live_stats.json"""
        try:
            # Используем to_thread чтобы не блокировать asyncio
            await asyncio.to_thread(self._sync_write_stats, stats)
        except Exception as e:
            logger.error(f"Failed to write live stats: {e}")
            
    def _sync_write_stats(self, stats: Dict):
        """Синхронная запись с atomic rename"""
        tmp_path = self.stats_path + ".tmp"
        try:
            with open(tmp_path, 'w') as f:
                json.dump(stats, f, default=str)
            # Atomic replace (работает на Windows и Unix)
            Path(tmp_path).replace(self.stats_path)
        except Exception as e:
            logger.error(f"Sync write failed: {e}")
            # Cleanup temp file если остался
            if Path(tmp_path).exists():
                Path(tmp_path).unlink(missing_ok=True)
                
    async def _flush_trades(self, force: bool = False):
        """Append trades к history файлу"""
        if not self._trade_buffer:
            return
            
        try:
            await asyncio.to_thread(self._sync_append_trades)
            self._trade_buffer.clear()
        except Exception as e:
            logger.error(f"Failed to flush trades: {e}")
            if force:
                # Emergency: пробуем записать хоть что-то
                self._emergency_sync_write()
                
    def _sync_append_trades(self):
        """Синхронное append к trade_history.json"""
        # Copilot: текущий формат - JSON array или JSONL?
        # Предполагаем, что Streamlit читает JSON array (как обычно)
        # Для append в JSON array нужно прочитать, дописать, записать
        # Для production лучше перейти на JSONL, но пока поддерживаем совместимость
        
        try:
            if Path(self.history_path).exists():
                with open(self.history_path, 'r') as f:
                    data = json.load(f)
                if not isinstance(data, list):
                    data = []
            else:
                data = []
                
            data.extend(self._trade_buffer)
            
            # Ограничиваем размер файла (последние 1000 сделок)
            if len(data) > 1000:
                data = data[-1000:]
                
            tmp_path = self.history_path + ".tmp"
            with open(tmp_path, 'w') as f:
                json.dump(data, f, default=str)
            Path(tmp_path).replace(self.history_path)
            
        except Exception as e:
            logger.error(f"Trade history append failed: {e}")
            raise
            
    def _emergency_sync_write(self):
        """Fallback при аварийном завершении"""
        try:
            # Пытаемся хотя бы сохранить буфер в отдельный файл
            emergency_path = self.history_path + ".emergency"
            with open(emergency_path, 'a') as f:
                for trade in self._trade_buffer:
                    f.write(json.dumps(trade, default=str) + "\n")
            logger.warning(f"Emergency write to {emergency_path}")
        except Exception as e:
            logger.critical(f"Emergency write failed: {e}")
			
Интеграция в core.py (адаптированная)
# В начале run():
stats_writer = StatsWriter(cfg)
await stats_writer.start()

# ... в цикле при закрытии сделки ...
for closed in closed_results:
    risk.register_closed_position(symbol, exchange)
    risk.update(closed)
    dashboard.update(closed)
    
    # Добавляем запись в writer
    stats_writer.log_trade({
        "symbol": symbol,
        "exchange": exchange,
        "pnl": closed["pnl"],
        "result": closed["result"],
        "direction": closed["direction"],
        "confidence": closed.get("confidence"),
        "entry_price": closed.get("entry_price"),
        "exit_price": closed.get("exit_price"),
    })
    
    # ... drift и retrain логика ...

# ... в конце итерации (после обработки всех символов) ...
# Обновляем live stats
stats_writer.update_live_stats({
    "balance": router.paper_balance if mode == "paper" else risk.current_balance,
    "open_positions": len(router.paper_positions),
    "daily_pnl": risk.daily_pnl,
    "unrealized_pnl": risk.unrealized_pnl,
    "last_signal_symbol": signal.symbol if signal else None,
    "last_signal_direction": signal.direction if signal else 0,
    "drift_alerts": drift_status.alerts if drift_status else [],
    "mtf_blocks": mtf_block_count,  # можно считать в цикле
})

# ... в finally/shutdown ...
await stats_writer.stop()

Что добавить в config.py
"monitor": {
    "live_stats_path": "data/live_stats.json",       # backward compat
    "trade_history_path": "data/trade_history.json", # backward compat
    "flush_interval_sec": 5,
    "max_history_trades": 1000,  # ограничение размера файла
}

Ключевые решения (Trade-offs)
| Проблема                 | Решение                          | Обоснование                                                    |
| ------------------------ | -------------------------------- | -------------------------------------------------------------- |
| **Пути**                 | Оставляем `data/live_stats.json` | Copilot прав — не ломаем существующий dashboard                |
| **Timestamp**            | Epoch seconds (`int`)            | Совместимость с `pd.to_datetime(..., unit='s')`                |
| **Trade History формат** | JSON array (bounded)             | Пока поддерживаем текущий формат. JSONL — в Phase 2            |
| **Async I/O**            | `asyncio.to_thread()`            | Нет зависимости от `aiofiles`, работает с текущим Python 3.10+ |
| **Atomic write**         | tmp + replace                    | Защита от "обрубленного" JSON при падении                      |
| **Graceful degradation** | try/except + logger              | При ошибке записи торговля продолжается                        |

План реализации Stage 4 (Acceptance Criteria)
PR-A: Minimal Compatible Writer
Создать stats_writer.py с кодом выше
Интегрировать в core.py (без изменений в Streamlit)
Добавить monitor секцию в config.py
Тест: запустить paper mode на 5 минут, проверить что файлы обновляются и dashboard их видит
PR-B: Optimization (опционально, позже)
Переход на JSONL для trade_history
Обновление Streamlit для поддержки обоих форматов
Добавление aiofiles если profiling покажет необходимость
Проверка перед мержем
[ ] python -m unittest tests.test_stats_writer (нужно создать базовый тест)
[ ] Paper mode запускается без ошибок
[ ] Файлы data/live_stats.json и data/trade_history.json создаются и обновляются
[ ] Streamlit отображает данные корректно
[ ] При kill -9 (симуляция падения) файлы не корраптируются (atomic write работает)
Итог: Этот подход удовлетворяет требованиям non-blocking writes, но не ломает существующую инфраструктуру. Мы получаем надежную телеметрию без риска для trading loop.
