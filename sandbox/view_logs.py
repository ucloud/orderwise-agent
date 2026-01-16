#!/usr/bin/env python3
"""
查看 Sandbox 中 MCP 服务器的日志和状态

使用方法:
    python view_logs.py <sandbox_id> [选项]

选项:
    --tail         实时跟踪日志（类似 tail -f）
    --startup      只查看启动日志
    --all          查看所有日志（启动日志 + 项目日志）
    --check        检查服务器状态（进程、端口、连接等）
"""

import argparse
import os
import sys
import time
from ucloud_sandbox import Sandbox


def view_startup_log(sandbox: Sandbox, tail: bool = False):
    """查看启动日志（/tmp/mcp_server.log）"""
    print("=" * 60)
    print("启动日志 (/tmp/mcp_server.log)")
    print("=" * 60)
    
    if tail:
        print("实时跟踪日志（按 Ctrl+C 退出）...\n")
        try:
            last_size = 0
            while True:
                result = sandbox.commands.run("wc -c /tmp/mcp_server.log 2>/dev/null | awk '{print $1}' || echo '0'", timeout=10)
                current_size = int(result.stdout.strip() or '0')
                
                if current_size > last_size:
                    result = sandbox.commands.run(f"tail -c +{last_size+1} /tmp/mcp_server.log 2>/dev/null || echo ''", timeout=10)
                    if result.stdout.strip():
                        print(result.stdout, end='', flush=True)
                    last_size = current_size
                
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n停止跟踪")
    else:
        result = sandbox.commands.run("tail -100 /tmp/mcp_server.log 2>/dev/null || echo '无日志文件'", timeout=10)
        print(result.stdout)


def view_project_logs(sandbox: Sandbox, tail: bool = False):
    """查看项目日志（/workspace/orderwise-agent/logs/）"""
    print("\n" + "=" * 60)
    print("项目日志 (/workspace/orderwise-agent/logs/)")
    print("=" * 60)
    
    # 列出日志文件
    result = sandbox.commands.run("ls -lht /workspace/orderwise-agent/logs/*.log 2>/dev/null | head -10 || echo '无日志文件'", timeout=10)
    if "无日志文件" not in result.stdout:
        print("日志文件列表:")
        print(result.stdout)
        
        if tail:
            print("\n实时跟踪最新日志文件（按 Ctrl+C 退出）...\n")
            try:
                while True:
                    latest = sandbox.commands.run("ls -t /workspace/orderwise-agent/logs/*.log 2>/dev/null | head -1", timeout=10)
                    if latest.stdout.strip():
                        result = sandbox.commands.run(f"tail -20 {latest.stdout.strip()} 2>/dev/null || echo ''", timeout=10)
                        if result.stdout.strip():
                            print(result.stdout, end='', flush=True)
                    time.sleep(2)
            except KeyboardInterrupt:
                print("\n\n停止跟踪")
        else:
            # 查看最新日志文件的内容
            latest = sandbox.commands.run("ls -t /workspace/orderwise-agent/logs/*.log 2>/dev/null | head -1", timeout=10)
            if latest.stdout.strip():
                log_file = latest.stdout.strip()
                print(f"\n最新日志文件: {log_file}")
                result = sandbox.commands.run(f"tail -50 {log_file} 2>/dev/null || echo '无内容'", timeout=10)
                print(result.stdout)
    else:
        print("无日志文件")


def check_status(sandbox: Sandbox):
    """检查服务器状态"""
    print("=" * 60)
    print("1. 检查进程")
    print("=" * 60)
    result = sandbox.commands.run("ps aux | grep -v grep | grep order_wise_mcp_server || true", timeout=10)
    if result.stdout.strip():
        print("进程运行中:")
        print(result.stdout)
    else:
        print("进程未找到")
    
    print("\n" + "=" * 60)
    print("2. 检查端口")
    print("=" * 60)
    result = sandbox.commands.run("netstat -tlnp 2>/dev/null | grep 8703 || ss -tlnp 2>/dev/null | grep 8703 || echo '未监听'", timeout=10)
    if "8703" in result.stdout:
        print("端口监听中:")
        print(result.stdout)
    else:
        print("端口 8703 未监听")
    
    print("\n" + "=" * 60)
    print("3. 测试 HTTP 连接")
    print("=" * 60)
    result = sandbox.commands.run("curl -s -w '\nHTTP状态码: %{http_code}\n' http://localhost:8703/ 2>&1 || echo '连接失败'", timeout=10)
    print(result.stdout)
    
    print("\n" + "=" * 60)
    print("4. 检查环境变量")
    print("=" * 60)
    result = sandbox.commands.run("cd /workspace/orderwise-agent && source env.sh && env | grep PHONE_AGENT", timeout=10)
    print(result.stdout)


def main():
    parser = argparse.ArgumentParser(description="查看 Sandbox 中 MCP 服务器的日志和状态")
    parser.add_argument("sandbox_id", help="Sandbox ID")
    parser.add_argument("--tail", action="store_true", help="实时跟踪日志")
    parser.add_argument("--startup", action="store_true", help="只查看启动日志")
    parser.add_argument("--all", action="store_true", help="查看所有日志")
    parser.add_argument("--check", action="store_true", help="检查服务器状态")
    
    args = parser.parse_args()
    
    if not os.getenv("AGENTBOX_API_KEY"):
        print("错误: 请设置环境变量 AGENTBOX_API_KEY")
        sys.exit(1)
    
    print(f"连接到 Sandbox: {args.sandbox_id}\n")
    sandbox = Sandbox.connect(sandbox_id=args.sandbox_id)
    
    if args.check:
        check_status(sandbox)
    elif args.startup:
        view_startup_log(sandbox, tail=args.tail)
    elif args.all:
        view_startup_log(sandbox, tail=False)
        view_project_logs(sandbox, tail=False)
    else:
        view_project_logs(sandbox, tail=args.tail)


if __name__ == "__main__":
    main()

