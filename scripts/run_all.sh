#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -d .venv ]]; then
  echo "未找到 .venv，请先执行 scripts/install_and_check.sh"
  exit 1
fi

source .venv/bin/activate

if [[ ! -f .env && -f .env.example ]]; then
  cp .env.example .env
  echo "已自动复制 .env.example -> .env"
fi

cleanup() {
  echo "停止服务中..."
  [[ -n "${BACK_PID:-}" ]] && kill "$BACK_PID" >/dev/null 2>&1 || true
  [[ -n "${FRONT_PID:-}" ]] && kill "$FRONT_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

python backend/main.py &
BACK_PID=$!

if command -v pnpm >/dev/null 2>&1; then
  (cd BillNote_frontend && pnpm dev --host 0.0.0.0) &
  FRONT_PID=$!
else
  echo "pnpm 未安装，仅启动后端。"
fi

wait
