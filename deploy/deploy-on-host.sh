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

sudo nginx -t
sudo systemctl reload nginx

echo "deployed ${DEPLOY_ROOT} on port ${DEPLOY_PORT} for ${DEPLOY_SERVER_NAME}"
