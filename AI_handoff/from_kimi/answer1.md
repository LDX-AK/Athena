Пользователь загрузил файлы для ревью:
Athena_TZ.md - техническое задание
change_history.md - история изменений
drift_monitor.py - монитор деградации модели
for_kimi.md - сопроводительное письмо с контекстом и вопросами
retrain_policy.py - политика переобучения
router.py - исполнение ордеров
Основные вопросы из for_kimi.md:
Достаточно ли robust логика baseline cold-start для периодов с редкими сделками?
Достаточен ли critical-alert quorum или нужен weighted severity?
Нужен ли cooldown bypass для экстремальных изменений режима?
Есть ли failure mode в propagation confidence от router к trade_history?
Я должен провести code review этих файлов, сфокусировавшись на edge cases и качестве политики.
Давайте проанализируем каждый файл:
drift_monitor.py:
Использует скользящее окно из N сделок (window_trades)
Базовый снимок делается при первом полном окне
Проверяет относительное снижение метрик (winrate_drop, confidence_drop, sharpe_drop)
Проверяет режим волатильности (умножение на volatility_multiplier)
Проверяет серию убытков (consecutive_losses)
Использует consecutive_alerts для триггера drift_detected
retrain_policy.py:
Проверяет weekly budget (max_retrains_per_week)
Проверяет cooldown между retrains
Проверяет scheduled trigger (по дням)
Для drift trigger требует critical_alerts_required критических алертов
Имеет dry_run режим
router.py:
Передает confidence в результаты сделок (paper и live)
В paper режиме сохраняет confidence в позиции и возвращает при закрытии
Теперь отвечу на конкретные вопросы:
Baseline cold-start:
Проблема: при редких сделках (например, 1 сделка в день), window_trades=30 займет 30 дней
Текущая логика: ждет полного окна, делает baseline, потом начинает отслеживать дрейф
Проблема: если рынок изменится во время накопления первого окна, baseline будет "испорчен" новым режимом
Предложение: добавить time-based fallback или минимальный порог для baseline
Critical-alert quorum vs weighted severity:
Сейчас: простой подсчет критических алертов (SHARPE_DRIFT, REGIME_VOLATILITY, LOSS_STREAK, SHARPE_FLOOR)
Проблема: LOSS_STREAK + SHARPE_DRIFT считается так же как REGIME_VOLATILITY + SHARPE_FLOOR, хотя веса должны быть разными
Предложение: добавить веса алертам для более точной оценки severity
Cooldown bypass:
Сейчас: жесткий cooldown блокирует любой retrain
Проблема: при резком краше рынка (черный лебедь) система не переобучится вовремя
Предложение: emergency override при комбинации критических алертов с высокой severity
Confidence propagation:
В router.py confidence берется из signal и передается в позицию
При закрытии confidence возвращается из позиции
Проблема: если позиция была открыта до обновления кода (legacy), get("confidence", 0.0) вернет 0.0, что испортит статистику
Проблема: в live режиме confidence тоже передается, но нет гарантии, что он сохраняется в той же структуре
Теперь составлю подробный ответ с рекомендациями.

Отлично, материал получил. Провел ревью кода и подготовил разбор по вашим вопросам.
🔍 Code Review: Drift Control & Execution
1. Baseline Cold-Start Logic (достаточно ли robust?)
Текущая реализация:
Ждет ровно window_trades сделок для первого baseline
Игнорирует time-based деградацию во время "прогрева"
Edge Case — "Медленная смерть":
Если window_trades=30, а сигналы разреженные (1-2 сделки в день), baseline собирается 2-3 недели. Если рынок начал меняться на 15-й сделке, baseline будет "захвачен" на границе двух режимов, и дрейф будет детектироваться с задержкой.
Рекомендация — Time-Decay Baseline:
def _should_update_baseline(self, checks: Dict, trade_count: int) -> bool:
    """
    Обновляем baseline если:
    1. Прошло >7 дней с момента первого capture ИЛИ
    2. Метрики улучшились значительно (новый "хороший" режим)
    """
    if not hasattr(self, '_baseline_timestamp'):
        return False
    
    days_since_baseline = (datetime.now(timezone.utc) - self._baseline_timestamp).days
    
    # Если текущие метрики лучше baseline на 20% — обновляем baseline
    improvement = (checks['win_rate'] > self._baseline_checks['win_rate'] * 1.2 and 
                   checks['sharpe'] > self._baseline_checks['sharpe'] * 1.2)
    
    return days_since_baseline > 7 or improvement
	Дополнительно: Сериализуйте _baseline_checks в JSON при graceful shutdown, чтобы рестарт не сбрасывал обучение baseline.
	
2. Critical-Alert Quorum vs Weighted Severity
Текущая проблема:
critical_count = len(set(alerts) & self.critical_alerts)
if critical_count >= self.critical_alerts_required:

LOSS_STREAK (5 убытков подряд) и SHARPE_DRIFT имеют одинаковый "вес" = 1, хотя по сути это разная степень критичности.
Предложение — Severity Score:
ALERT_SEVERITY = {
    "SHARPE_FLOOR": 1,        # Базовая защита
    "WINRATE_FLOOR": 1,
    "WINRATE_DRIFT": 2,       # Относительное снижение
    "CONFIDENCE_DRIFT": 2,
    "SHARPE_DRIFT": 3,        # Критично для risk-adjusted returns
    "REGIME_VOLATILITY": 3,   # Смена режима
    "LOSS_STREAK": 4,         # Самый опасный (маркет против нас)
    "PROFIT_FACTOR_FLOOR": 2,
}

def evaluate(self, ...):
    # ... existing code ...
    
    severity_score = sum(ALERT_SEVERITY.get(a, 1) for a in alerts)
    
    # В retrain_policy.py:
    # Вместо critical_alerts_required используем severity_threshold
    if severity_score >= self.critical_severity_threshold:  # например, 6
        return RetrainDecision(True, f"high-severity:{severity_score}")
		
		Почему это важно: LOSS_STREAK=5 + REGIME_VOLATILITY = severity 7 (критично), а WINRATE_DRIFT + CONFIDENCE_DRIFT = 4 (можно подождать).
3. Cooldown Bypass для Extreme Regime Breaks
Текущая проблема:
if cooldown_left.total_seconds() > 0:
    return RetrainDecision(False, f"cooldown-active...")
	
	При резком крэше (например, BTC -15% за час) система будет ждать cooldown_hours (24ч), теряя деньги на устаревшей модели.
Решение — Emergency Override:
def evaluate(self, drift_detected: bool = False, alerts: List[str] | None = None, 
             severity_score: int = 0) -> RetrainDecision:
    # ... existing checks ...
    
    # Emergency bypass: комбинация LOSS_STREAK + REGIME_VOLATILITY + высокий severity
    is_emergency = (
        "LOSS_STREAK" in alerts and 
        "REGIME_VOLATILITY" in alerts and 
        severity_score >= 7
    )
    
    if is_emergency:
        # Проверяем emergency rate limit (не чаще 1 раза в 6 часов)
        last_emergency = getattr(self, '_last_emergency_retrain', None)
        if last_emergency and (now - last_emergency).hours < 6:
            return RetrainDecision(False, "emergency-rate-limited")
        
        self._last_emergency_retrain = now
        return RetrainDecision(True, "EMERGENCY-REGIME-BREAK")

    # ... standard logic ...
	Важно: Логировать такие события отдельным ERROR уровнем — это индикатор того, что рынок вышел за пределы обучающей выборки.
4. Confidence Propagation — Failure Modes
В router.py нашел потенциальную проблему:
# В close_paper_position:
"confidence": pos.get("confidence", 0.0),

Bug Scenario:
Старые позиции (открытые до обновления) не имеют ключа "confidence" в словаре
pos.get("confidence", 0.0) вернет 0.0
Drift monitor увидит avg_confidence=0.0 и триггерит CONFIDENCE_DRIFT
Ложный retrain
Fix:
# В close_paper_position:
confidence = pos.get("confidence")
if confidence is None:
    # Legacy position или ошибка — не включаем в статистику drift
    logger.warning("Closing position without confidence tracking: %s", key)
    # Можно либо пропустить эту сделку в drift monitor, 
    # либо использовать последний известный confidence из сигнала

Дополнительно в drift_monitor.py:
def evaluate(self, trade_history: List[Dict]) -> DriftStatus:
    # Фильтруем сделки без confidence для чистоты метрики
    valid_trades = [t for t in trade_history if t.get("confidence") is not None]
    if len(valid_trades) < self.window_trades * 0.8:  # менее 80% с confidence
        logger.warning("Insufficient confidence data in window")
        return DriftStatus(False, 0, {}, [], ["insufficient-data"])
    
    recent = valid_trades[-self.window_trades:]
	
	5. Дополнительные замечания по коду
A. Sharpe Ratio расчет (div by zero protection)
sharpe = mean / (std + 1e-9)
При mean = -0.001, std = 1e-9 получится sharpe = -1e6, что сломает логику sharpe_drop.
Fix:
# Минимальный meaningful sharpe требует минимальной волатильности
if std < 1e-6:
    sharpe = 0.0  # Недостаточно данных для оценки
else:
    sharpe = mean / std

B. Volatility Regime Detection
Сейчас сравнивается recent_volatility (последние 20 сделок) с baseline_volatility (все окно). Если сделки редкие, "recent" может охватывать 3 дня, а baseline — 30 дней. Это нечестное сравнение.
Fix: Используйте time-based volatility (ATR из цен), не trade-based.
C. Router — SL/TP Logic Bug
hit_sl = (direction == 1 and low_price <= sl) or (direction == -1 and high_price >= sl)

Для short позиции (direction == -1): SL выше entry. Если high_price >= sl, значит цена поднималась до SL. Это корректно.
Но проверьте, что low_price/high_price приходят из правильного таймфрейма (1m свечи), иначе при гэпе вы можете пропустить срабатывание SL между свечами.

Итоговые рекомендации (приоритет)
P0 (фиксить сейчас):
Confidence default value — убрать 0.0 как fallback, использовать None и фильтровать
Sharpe div by zero — защита от std < 1e-6
Emergency override — добавить bypass cooldown для комбинации LOSS_STREAK + VOLATILITY
P1 (улучшение robustness):
4. Severity scoring — заменить простой счетчик алертов на weighted sum
5. Time-decay baseline — обновлять baseline при значительном улучшении метрик или по времени
P2 (оптимизация):
6. Persist baseline — сохранять в файл между рестартами
7. ATR-based volatility — более точный regime detection чем trade-based std
В текущем виде система уже production-ready для paper trading, но эти правки сделают её устойчивой к "черным лебедям" и legacy-данным.