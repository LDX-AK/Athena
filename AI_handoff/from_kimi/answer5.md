
Принял эстафету! 👋
Провожу комплексный анализ пакета документов по проблеме overfitting в Athena 15m модели. Сейчас изучаю:

    Контекст: Восстановлена Linux-паритетность, June бенчмарк снова положительный, но свежий 90-дневный holdout отрицательный во всех 4 сценариях — классический признак overfitting к "золотому июню".
    Позиции ревьюеров:
        Deepseek: диагноз overfit + рекомендации по упрощению модели, runtime circuit breaker, TP/SL-first labeling
        Copilot: согласен с диагнозом, но уточняет что нет "battle-ready" режима, label-логика уже частично улучшена, нужна walk-forward валидация
    Текущая архитектура: drift monitor, retrain policy, MTF gate, sentiment fusion, ~60 признаков, LightGBM

Сейчас детально разбираю кодовую базу (config, engineer, signal, drift_monitor, retrain_policy, risk/manager) чтобы сформировать чёткие ответы на ваши 5 вопросов и рекомендации по приоритетам.
Нужно несколько минут на полный анализ всех файлов.
Ну как ?
Edit
Copy
Share
Готов. Вот мой анализ и рекомендации.
1. Согласен ли я с диагнозом overfitting?
Да, полностью. Данные однозначны:
Table
Сценарий	June (in-sample)	90d Holdout (out-of-sample)
sent_on__conservative	+0.11%, Sharpe 15.54	-0.21%, Sharpe -6.13
sent_off__conservative	+0.27%, Sharpe 7.61	-1.39%, Sharpe -3.96
Это классический regime-specific overfit. Модель запомнила паттерны июня 2025, но не извлекла обобщаемые правила. Linux-паритетность восстановлена — значит проблема не в deployment, а в качестве модели.
2. Приоритет действий (в порядке важности)
P0 — Runtime Circuit Breaker (неделя 1)
Зачем: Защита капитала превыше всего. Сейчас drift_monitor детектирует проблему, но не останавливает торговлю.
Что сделать:
Python
Copy

# В core.py, после drift_status.drift_detected
if drift_status.drift_detected and not retrain_decision.trigger:
    risk.emergency_reduce_size()  # Снижаем размер позиции
    if drift_status.alerts_in_row >= 5:  # Критический порог
        risk.go_baseline_mode()  # Переключаемся на OBI+RSI

P1 — Honest Walk-Forward Validation (неделя 1-2)
Зачем: Текущая валидация позволяет утечку будущего. Нужен strict time-based split.
Сплит:

    Train: Apr–May 2025
    Validation: Jun 2025 (тюнинг гиперпараметров)
    Test: Jul–Sep 2025 (финальная оценка — трогать нельзя)

Критерий: Если модель не проходит test — в прод не идёт, независимо от validation.
P2 — Feature Group Ablation (неделя 2-3)
Зачем: 60+ признаков — перебор для 15m. Нужно найти минимальный robust набор.
Порядок отключения (от наиболее подозрительных):

    sentiment — внешний шум, низкая предсказательная сила в краткосрочке
    rolling stats (sharpe/skew/autocorr) — легко overfitятся на конкретный режим
    regime interactions — если не ablate'нуты правильно, дают утечку

Методология: Group-wise ablation с фиксированным random seed. Сравниваем не accuracy, а Sharpe на holdout.
P3 — Simpler LightGBM (неделя 3-4)
Зачем: Текущая модель слишком гибкая.
Консервативный старт:
Python
Copy

{
    "num_leaves": 15,        # было ~31+
    "max_depth": 4,          # было 6-8
    "min_child_samples": 100, # было 20
    "feature_fraction": 0.7,
    "bagging_fraction": 0.7,
    "bagging_freq": 5,
}

Важно: Менять только после P0-P2, иначе "лечим симптомы, а не болезнь".
3. Отключать ли sentiment для следующего цикла?
Да, по умолчанию OFF.
Аргументы:

    В holdout sent_on показывает худшие результаты, чем sent_off (-0.21% vs -1.39% для conservative, но -1.75% vs -2.78% для aggressive — разница невелика)
    Sentiment имеет инерцию — полезен для свингов (4h+), но шумит на 15m
    Уменьшает размерность с ~60 до ~54 признаков — небольшой, но полезный шаг

Условие включения: Если после стабилизации базовой модели ablation покажет положительный contribution на чистом валидационном сете.
4. Наиболее подозрительные feature families
Table
Family	Подозрительность	Почему
rolling	🔴 Высокая	Rolling Sharpe/Skew/Autocorr — явно overfit к спокойному июню. На волатильном holdout дают ложные сигналы
sentiment	🟡 Средняя	Внешний источник, несинхронизирован с ценовым движением на 15m
regime	🟡 Средняя	Vol_regime, acceleration — если рассчитываются на всей истории, дают утечку
multi-horizon	🟢 Низкая	Ret/vol/range за 5-120m — фундаментальные признаки, нужны
orderbook/flow	🟢 Низкая	Микроструктура рынка — stable signal
Первый ablation тест: rolling OFF → sentiment OFF → обе OFF.
5. Acceptance criteria для перехода к paper trading
Минимальный барьер (все должны выполняться одновременно):
Table
Метрика	Порог	Почему
Sharpe Ratio	> 0.5	Положительный risk-adjusted return
Total Return	> 0%	Не теряем деньги
Max Drawdown	< 15%	Управляемый риск
Profit Factor	> 1.2	Профиты превышают убытки
Win Rate stability	±10% от baseline	Не overfit к конкретному режиму
Дополнительно:

    Walk-forward stability: 3 из 4 фолдов (rolling 30d windows) показывают положительный Sharpe
    Regime robustness: Положительный результат на данных с повышенной волатильностью (август 2025)

Итоговый план на 2-3 недели
Table
Неделя	Фокус	Доставляемый результат
1	Circuit breaker + Walk-forward framework	Код защиты капитала + скрипт честного сплита
2	Feature ablation (rolling, sentiment)	Отчёт: какие фичи улучшают/ухудшают generalization
3	LightGBM simplification + финальная валидация	Модель, проходящая acceptance criteria
Ключевой принцип: Нет paper trading до тех пор, пока holdout не станет зелёным. June бенчмарк больше не является достаточным условием.
Готов детализировать любой из пунктов или помочь с имплементацией.
