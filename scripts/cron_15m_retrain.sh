#!/bin/bash
# Cron wrapper for 15m model weekly retrain
# Add to crontab: 0 2 * * 0 /home/athena/Athena/scripts/cron_15m_retrain.sh

ATHENA_HOME="/home/athena/Athena"
VENV="${ATHENA_HOME}/.venv/bin/python"
SCRIPT="${ATHENA_HOME}/train_model_tf.py"
CSV="${ATHENA_HOME}/data/raw/ohlcv/BTCUSDT_15m_latest.csv"
MODEL="${ATHENA_HOME}/athena/model/athena_brain_15m.pkl"
RESULTS_DIR="${ATHENA_HOME}/data/results"
TIMESTAMP=$(date +'%Y%m%d_%H%M%S')
LOG_FILE="${RESULTS_DIR}/train_15m_cron_${TIMESTAMP}.log"
ERR_FILE="${RESULTS_DIR}/train_15m_cron_${TIMESTAMP}.err"

mkdir -p "${RESULTS_DIR}"

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Starting 15m retrain..." > "${LOG_FILE}"

${VENV} -u "${SCRIPT}" \
  --timeframe 15m \
  --csv-path "${CSV}" \
  --model-path "${MODEL}" \
  --max-rows 8000 \
  --csv-window last \
  >> "${LOG_FILE}" 2>> "${ERR_FILE}"

EXIT_CODE=$?

if [ ${EXIT_CODE} -eq 0 ]; then
  echo "[CRON-OK] 15m retrain completed successfully at $(date +'%Y-%m-%d %H:%M:%S')" >> "${LOG_FILE}"
  # Optional: trigger backtest or alert
else
  echo "[CRON-ERROR] 15m retrain failed with exit code ${EXIT_CODE}" >> "${ERR_FILE}"
  exit ${EXIT_CODE}
fi
