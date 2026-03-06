#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/5] 检查 Python..."
python3 --version

echo "[2/5] 创建后端虚拟环境..."
python3 -m venv .venv
source .venv/bin/activate

echo "[3/5] 安装后端依赖..."
pip install --upgrade pip
pip install -r backend/requirements.txt

echo "[4/5] 安装前端依赖..."
if command -v pnpm >/dev/null 2>&1; then
  (cd BillNote_frontend && pnpm install)
else
  echo "未检测到 pnpm，请先安装：npm i -g pnpm"
fi

echo "[5/5] 环境检查完成。"
echo "可执行 scripts/run_all.sh 一键启动。"
