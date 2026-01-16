#!/bin/bash
# Start MCP server and view logs in tmux with 3 columns (参照 mobileagent 方式)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Find conda
CONDA_INIT=""
for base in "$HOME/miniconda3" "$HOME/anaconda3"; do
    init_path="$base/etc/profile.d/conda.sh"
    if [ -f "$init_path" ]; then
        CONDA_INIT="$init_path"
        break
    fi
done

CONDA_CMD=""
if [ -n "$CONDA_INIT" ]; then
    CONDA_CMD="source '$CONDA_INIT' && conda activate waimai"
else
    CONDA_CMD="conda activate waimai"
fi

# Set PYTHONPATH
export PYTHONPATH="$PYTHONPATH:$SCRIPT_DIR"

# 加载环境变量配置（env.sh）
if [ -f "$SCRIPT_DIR/env.sh" ]; then
    source "$SCRIPT_DIR/env.sh"
    echo "[MCP Server] 已加载环境变量配置: env.sh"
else
    echo "[MCP Server] 警告: env.sh 不存在，使用默认配置"
fi

# Log configuration
LOG_DIR="${ORDERWISE_LOG_DIR:-${SCRIPT_DIR}/logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/mcp_$(date +%Y%m%d_%H%M%S).log"
PID_FILE="${TMPDIR:-/tmp}/mcp-server.pid"
SESSION_NAME="mcp-server"

# 清理旧日志（保留最近100个）
ls -t "$LOG_DIR"/mcp_*.log 2>/dev/null | tail -n +101 | xargs rm -f 2>/dev/null

# Cleanup function
cleanup() {
    # Kill all MCP server processes (more robust than PID file)
    pkill -f "order_wise_mcp_server.py" 2>/dev/null
    sleep 1
    pkill -9 -f "order_wise_mcp_server.py" 2>/dev/null
    
    # Also clean up PID file if exists
    if [ -f "$PID_FILE" ]; then
        rm -f "$PID_FILE"
    fi
    
    TMP_BASE="${TMPDIR:-/tmp}"
    rm -f "${TMP_BASE}/mcp-filter-1.sh" "${TMP_BASE}/mcp-filter-2.sh" "${TMP_BASE}/mcp-filter-3.sh"
    tmux kill-session -t "$SESSION_NAME" 2>/dev/null
    exit 0
}

# Set up signal handlers
trap cleanup INT TERM EXIT

# Start server in background
if [ -n "$CONDA_INIT" ]; then
    source "$CONDA_INIT"
fi
conda activate waimai 2>/dev/null || true

python mcp_mode/mcp_server/order_wise_mcp_server.py > "$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

# Wait for server to start and show startup info
echo "等待 MCP 服务器启动..."
for i in {1..30}; do
    if grep -q "Uvicorn running" "$LOG_FILE" 2>/dev/null; then
        break
    fi
    sleep 0.5
done

# Display startup info before splitting panes
if [ -f "$LOG_FILE" ]; then
    echo ""
    echo "=========================================="
    echo "MCP 服务器启动信息:"
    echo "=========================================="
    cat "$LOG_FILE" 2>/dev/null
    echo ""
    echo "=========================================="
    echo "启动完成，正在创建 tmux 分 pane 显示..."
    echo "=========================================="
    sleep 1
fi

# Start tmux server if not running
if ! tmux has-session 2>/dev/null; then
    tmux start-server
    sleep 1
fi

# Kill existing session if exists
tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true
sleep 0.5

# Create temporary filter scripts to avoid complex quoting
TMP_BASE="${TMPDIR:-/tmp}"
FILTER_SCRIPT_1="${TMP_BASE}/mcp-filter-1.sh"
FILTER_SCRIPT_2="${TMP_BASE}/mcp-filter-2.sh"
FILTER_SCRIPT_3="${TMP_BASE}/mcp-filter-3.sh"

cat > "$FILTER_SCRIPT_1" << EOF1
#!/bin/bash
tail -n 500 "$LOG_FILE" 2>/dev/null | awk '/\[美团\]/ {in_section=1} /\[(京东外卖|淘宝闪购)\]/ {in_section=0} in_section {print "\033[33m" \$0 "\033[0m"}'
tail -f "$LOG_FILE" 2>/dev/null | awk '/\[美团\]/ {in_section=1} /\[(京东外卖|淘宝闪购)\]/ {in_section=0} in_section {print "\033[33m" \$0 "\033[0m"}'
EOF1

cat > "$FILTER_SCRIPT_2" << EOF2
#!/bin/bash
tail -n 500 "$LOG_FILE" 2>/dev/null | awk '/\[京东外卖\]/ {in_section=1} /\[(美团|淘宝闪购)\]/ {in_section=0} in_section {print "\033[31m" \$0 "\033[0m"}'
tail -f "$LOG_FILE" 2>/dev/null | awk '/\[京东外卖\]/ {in_section=1} /\[(美团|淘宝闪购)\]/ {in_section=0} in_section {print "\033[31m" \$0 "\033[0m"}'
EOF2

cat > "$FILTER_SCRIPT_3" << EOF3
#!/bin/bash
tail -n 500 "$LOG_FILE" 2>/dev/null | awk '/\[淘宝闪购\]/ {in_section=1} /\[(美团|京东外卖)\]/ {in_section=0} in_section {print "\033[38;5;208m" \$0 "\033[0m"}'
tail -f "$LOG_FILE" 2>/dev/null | awk '/\[淘宝闪购\]/ {in_section=1} /\[(美团|京东外卖)\]/ {in_section=0} in_section {print "\033[38;5;208m" \$0 "\033[0m"}'
EOF3

chmod +x "$FILTER_SCRIPT_1" "$FILTER_SCRIPT_2" "$FILTER_SCRIPT_3"

# Create tmux session with first pane running server logs (美团)
tmux new-session -d -s "$SESSION_NAME" -c "$SCRIPT_DIR" "$FILTER_SCRIPT_1" || {
    echo "错误: 无法创建 tmux 会话"
    rm -f "$FILTER_SCRIPT_1" "$FILTER_SCRIPT_2" "$FILTER_SCRIPT_3"
    cleanup
    exit 1
}

# Wait for session to be ready
sleep 1

# Verify session exists
if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "错误: tmux 会话创建失败"
    rm -f "$FILTER_SCRIPT_1" "$FILTER_SCRIPT_2" "$FILTER_SCRIPT_3"
    cleanup
    exit 1
fi

# Split horizontally for second pane (京东外卖)
tmux split-window -h -t "${SESSION_NAME}:0" -c "$SCRIPT_DIR" "$FILTER_SCRIPT_2" || {
    echo "错误: 无法创建第二个 pane"
    rm -f "$FILTER_SCRIPT_1" "$FILTER_SCRIPT_2" "$FILTER_SCRIPT_3"
    cleanup
    exit 1
}

# Wait for second pane to be ready
sleep 1

# Split horizontally for third pane (淘宝闪购)
tmux split-window -h -t "${SESSION_NAME}:0.1" -c "$SCRIPT_DIR" "$FILTER_SCRIPT_3" || {
    echo "错误: 无法创建第三个 pane"
    rm -f "$FILTER_SCRIPT_1" "$FILTER_SCRIPT_2" "$FILTER_SCRIPT_3"
    cleanup
    exit 1
}

# Wait for all panes to be ready
sleep 1

# Wait a bit more for panes to be ready
sleep 1

# Set pane titles (only if session exists)
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    tmux select-pane -t "${SESSION_NAME}:0.0" -T "美团" 2>/dev/null
    tmux select-pane -t "${SESSION_NAME}:0.1" -T "京东外卖" 2>/dev/null
    tmux select-pane -t "${SESSION_NAME}:0.2" -T "淘宝闪购" 2>/dev/null
    
    # Set layout: 3 equal columns
    tmux select-layout -t "$SESSION_NAME" even-horizontal 2>/dev/null
    
    # Set up hook to cleanup when tmux session is killed
    tmux set-hook -t "$SESSION_NAME" session-closed "run-shell 'if [ -f $PID_FILE ]; then kill \$(cat $PID_FILE) 2>/dev/null; kill -9 \$(cat $PID_FILE) 2>/dev/null; rm -f $PID_FILE; fi'" 2>/dev/null
    
    # Add key binding to kill server (Ctrl+b, then Shift+K)
    tmux bind-key -T root K run-shell "if [ -f $PID_FILE ]; then kill \$(cat $PID_FILE) 2>/dev/null; kill -9 \$(cat $PID_FILE) 2>/dev/null; rm -f $PID_FILE; fi; tmux kill-session -t $SESSION_NAME" \; display-message "关闭服务器..." 2>/dev/null
fi

# Attach immediately (only if session exists)
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    tmux attach -t "$SESSION_NAME" 2>/dev/null || {
        echo "错误: 无法附加到 tmux 会话"
        cleanup
        exit 1
    }
else
    echo "错误: tmux 会话创建失败"
    cleanup
    exit 1
fi

# When tmux detaches, cleanup
cleanup

