#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

LOG_DIR="${ORDERWISE_LOG_DIR:-${SCRIPT_DIR}/logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/mcp_$(date +%Y%m%d_%H%M%S).log"

# 清理旧日志（保留最近100个）
ls -t "$LOG_DIR"/mcp_*.log 2>/dev/null | tail -n +101 | xargs rm -f 2>/dev/null

conda activate waimai 2>/dev/null || true
export PYTHONPATH="$PYTHONPATH:$SCRIPT_DIR"

# 加载环境变量配置（env.sh）
if [ -f "$SCRIPT_DIR/env.sh" ]; then
    source "$SCRIPT_DIR/env.sh"
    echo "[MCP Server] 已加载环境变量配置: env.sh"
else
    echo "[MCP Server] 警告: env.sh 不存在，使用默认配置"
fi

echo "MCP Server starting..."
echo "Log file: $LOG_FILE"

python mcp_mode/mcp_server/order_wise_mcp_server.py > "$LOG_FILE" 2>&1

