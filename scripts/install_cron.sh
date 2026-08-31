#!/usr/bin/env bash
# 安装每天 08:00 的 cron 任务（幂等，可重复执行）
# 用法: bash scripts/install_cron.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3 || command -v python)"
fi

LINE="0 8 * * * cd ${ROOT} && ${PYTHON} -m workbench.cli digest >> ${ROOT}/data/logs/cron.log 2>&1"

( crontab -l 2>/dev/null | grep -v "workbench.cli digest" || true; echo "$LINE" ) | crontab -

echo "✅ 已安装 cron 任务（每天 08:00）："
echo "   $LINE"
echo "查看: crontab -l    删除: crontab -e"
