#!/bin/bash
# Production deployment and cleanup checklist for 15m model

set -e

ATHENA_HOME="${1:-.}"

echo "=== Athena 15m Production Deployment ==="
echo "Home: ${ATHENA_HOME}"

# Step 1: Verify model exists and is recent
echo ""
echo "1. Verifying model artifact..."
if [ -f "${ATHENA_HOME}/athena/model/athena_brain_15m.pkl" ]; then
  SIZE=$(stat -f%z "${ATHENA_HOME}/athena/model/athena_brain_15m.pkl" 2>/dev/null || stat -c%s "${ATHENA_HOME}/athena/model/athena_brain_15m.pkl" 2>/dev/null || echo "?")
  MTIME=$(stat -f%Sm -t %Y-%m-%d "${ATHENA_HOME}/athena/model/athena_brain_15m.pkl" 2>/dev/null || stat -c%y "${ATHENA_HOME}/athena/model/athena_brain_15m.pkl" 2>/dev/null | cut -d' ' -f1 || echo "?")
  echo "  ✓ athena_brain_15m.pkl exists [SIZE=${SIZE}B, MTIME=${MTIME}]"
else
  echo "  ✗ athena_brain_15m.pkl NOT FOUND"
  exit 1
fi

# Step 2: Verify feature importance was saved
echo ""
echo "2. Verifying feature importance..."
if [ -f "${ATHENA_HOME}/athena/model/athena_brain_15m_feature_importance.json" ]; then
  echo "  ✓ athena_brain_15m_feature_importance.json exists"
else
  echo "  ⚠ Feature importance not found (non-critical)"
fi

# Step 3: Setup cron or systemd
echo ""
echo "3. Scheduler setup:"
echo "  Option A (cron): Add to crontab -e:"
echo "    0 2 * * 0 ${ATHENA_HOME}/scripts/cron_15m_retrain.sh"
echo ""
echo "  Option B (systemd): Copy service files and enable:"
echo "    sudo cp ${ATHENA_HOME}/scripts/athena_15m_retrain.{service,timer} /etc/systemd/system/"
echo "    sudo systemctl daemon-reload"
echo "    sudo systemctl enable athena_15m_retrain.timer"
echo "    sudo systemctl start athena_15m_retrain.timer"

# Step 4: Verify comparison scripts present
echo ""
echo "4. Verifying comparison scripts..."
for script in run_compare_15m.py run_compare_15m_fast.py; do
  if [ -f "${ATHENA_HOME}/${script}" ]; then
    echo "  ✓ ${script} present"
  else
    echo "  ⚠ ${script} missing"
  fi
done

# Step 5: Recommend cleanup
echo ""
echo "5. Cleanup recommendations:"
echo "  Archive old logs: tar czf data/results/logs_archive_$(date +%Y%m%d).tar.gz data/results/*.log"
echo "  Remove temporary artifacts: rm data/results/train_15m_expanded_*.log"
echo "  Keep production-only: run_compare_15m_fast.py (optimized)"

echo ""
echo "=== Deployment ready. Next: systemctl enable + start on Linux ==="
