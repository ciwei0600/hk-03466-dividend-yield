#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export SCRIPT_DIR
export DEPLOY_ROOT="${DEPLOY_ROOT:-${PROJECT_ROOT}}"
export DEPLOY_PORT="${DEPLOY_PORT:-80}"
export DEPLOY_SERVER_NAME="${DEPLOY_SERVER_NAME:-03466-dividend.43.167.235.131.nip.io}"

python3 - <<'PY' | sudo tee /etc/nginx/sites-available/hk-03466-dividend-yield >/dev/null
import os
from pathlib import Path

template = Path(os.environ["SCRIPT_DIR"]) / "nginx-site.conf.template"
content = template.read_text()
for key in ("DEPLOY_ROOT", "DEPLOY_PORT", "DEPLOY_SERVER_NAME"):
    content = content.replace("${" + key + "}", os.environ[key])
print(content, end="")
PY

sudo ln -sfn /etc/nginx/sites-available/hk-03466-dividend-yield \
  /etc/nginx/sites-enabled/hk-03466-dividend-yield

mkdir -p "${DEPLOY_ROOT}/runtime-data"

if [[ "${SKIP_DATA_UPDATE:-0}" != "1" ]]; then
  DATA_SERVER_API_BASE="${DATA_SERVER_API_BASE:-http://100.77.62.83:8010}" \
  DATA_SERVER_CONSUMER_ID="${DATA_SERVER_CONSUMER_ID:-cash-ranking}" \
  python3 "${DEPLOY_ROOT}/scripts/update-data.py"
fi

CRON_CMD="cd ${DEPLOY_ROOT} && DATA_SERVER_API_BASE=${DATA_SERVER_API_BASE:-http://100.77.62.83:8010} DATA_SERVER_CONSUMER_ID=${DATA_SERVER_CONSUMER_ID:-cash-ranking} /usr/bin/python3 scripts/update-data.py >> runtime-data/update-data.log 2>&1"
CRON_MARKER="# hk-03466-dividend-yield daily close update"
CRON_LINE="5 18 * * 1-5 ${CRON_CMD}"
((crontab -l 2>/dev/null || true) | grep -v -F "${CRON_MARKER}" | grep -v -F "scripts/update-data.py" || true; echo "${CRON_MARKER}"; echo "${CRON_LINE}") | crontab -

sudo nginx -t
sudo systemctl reload nginx

echo "deployed ${DEPLOY_ROOT} on port ${DEPLOY_PORT} for ${DEPLOY_SERVER_NAME}"
echo "installed daily update cron: ${CRON_LINE}"
