#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

LOG_DIR="${ORDERWISE_LOG_DIR:-${SCRIPT_DIR}/logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/listener_$(date +%Y%m%d_%H%M%S).log"

# 清理旧日志（保留最近100个）
ls -t "$LOG_DIR"/listener_*.log 2>/dev/null | tail -n +101 | xargs rm -f 2>/dev/null

echo "Listener mode starting..."
echo "Log file: $LOG_FILE"

MONGODB_CONNECTION="${MONGODB_CONNECTION_STRING:-}"
BASE_URL="${MODEL_BASE_URL:-http://localhost:4244/v1}"

if [ -z "$MONGODB_CONNECTION" ]; then
    echo "Error: MONGODB_CONNECTION_STRING environment variable is required"
    exit 1
fi

python main.py \
	--mongodb-listener \
	--mongodb-connection "$MONGODB_CONNECTION" \
	--base-url "$BASE_URL" \
	--parallel \
	--apps-config examples/apps_config.json \
	> "$LOG_FILE" 2>&1