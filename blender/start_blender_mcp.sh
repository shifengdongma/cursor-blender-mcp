#!/usr/bin/env bash

##
## 在 Ubuntu + GPU 机器上启动 Blender MCP 服务器的参考脚本
##
## 前置条件：
## - 已安装 Blender 4.x（例如通过 snap：sudo snap install blender --classic）
## - 已创建虚拟环境并在其中安装：mcp fastmcp numpy opencv-python pydantic
## - 已配置好 Xvfb / DISPLAY（若需要 Eevee 视口能力）
##

set -euo pipefail

# === 根据你的实际路径进行修改 ===
BLENDER_BIN="${BLENDER_BIN:-/snap/blender/current/blender}"
PROJECT_ROOT="${PROJECT_ROOT:-$HOME/blender_mcp}"
VENV_DIR="${VENV_DIR:-$HOME/blender_mcp_env}"

export PYTHONUNBUFFERED=1
export PYTHONPATH="$VENV_DIR/lib/python3.11/site-packages:${PYTHONPATH:-}"

# 如使用 Xvfb，可预先启动： Xvfb :1 -screen 0 1920x1080x24 &
# 这里假设外部已启动好虚拟显示
export DISPLAY="${DISPLAY:-:1}"

cd "$PROJECT_ROOT"

exec "$BLENDER_BIN" \
  --background \
  --python "$PROJECT_ROOT/blender/blender_agent.py"

